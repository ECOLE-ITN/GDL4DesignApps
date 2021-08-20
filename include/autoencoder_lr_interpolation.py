""" 
## LICENSE: GPL 3.0
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or 
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

## Scripts for interplating shapes in the latent space using the trained
parameters of the vanilla and variational 3D point cloud autoencoders
used for the research in:
- T. Rios, B. van Stein, S. Menzel, T. Bäck, B. Sendhoff, P. Wollstadt,
"Feature Visualization for 3D Point Cloud Autoencoders", 
International Joint Conference on Neural Networks (IJCNN), 2020
[https://www.honda-ri.de/pubs/pdf/4354.pdf]

- T. Rios, T. Bäck, B. van Stein, B. Sendhoff, S. Menzel, 
"On the Efficiency of a Point Cloud Autoencoder as a Geometric Representation
for Shape Optimization", 2019 IEEE Symposium Series on Computational Intelligence 
(SSCI), pp. 791-798, 2019.
[https://www.honda-ri.de/pubs/pdf/4199.pdf]


Pre-requisites:
 - Python      3.6.10
 - numpy       1.19.1
 - TensorFlow  1.14.0
 - TFLearn     0.3.2
 - cudatoolkit 10.1.168
 - cuDNN       7.6.5
 - Ubuntu      18.04
 - pandas      1.1.0
 - plotly      4.9.0
 - pyvista     0.29.1

Copyright (c)
Honda Research Institute Europe GmbH

Authors: Thiago Rios <thiago.rios@honda-ri.de>
"""

# ==============================================================================
## Import Libraries
# General purpose
import os
import os.path as osp
import time
import sys
import argparse

# Mathematical / Scientific tools
import numpy as np
import pandas as pd
import random
import tensorflow as tf

# Ploting
import matplotlib
matplotlib.use('tkagg')
import matplotlib.pyplot as plt
import plotly.graph_objs as go
from plotly.offline import download_plotlyjs, init_notebook_mode, plot, iplot
import pyvista as pv

# Achlioptas original implementation
from latent_3d_points.external.structural_losses.tf_approxmatch import\
    approx_match, match_cost
from latent_3d_points.external.structural_losses.tf_nndistance import\
    nn_distance

from preproc_scripts import data_part_tree as DataPart
from preproc_scripts import data_set_norm, pointcloud_sampling
from architecture_autoencoders import encoder_layer_gen, decoder_layer_gen,\
        vae_encoder_layer_gen, ENCODER, DECODER, vae_ENCODER, vae_DECODER

# ==============================================================================
### INITIALIZATION
## Get arguments from command line
parser = argparse.ArgumentParser(description='pc-ae training hyperparameters')
# Point cloud size
parser.add_argument('--N', type=int,\
        help='point cloud size')
# Size of the latent representation
parser.add_argument('--LR', type=int,\
        help='number of latent variables')
# GPU ID
parser.add_argument('--GPU', type=int,\
        help='GPU ID')
# Variational autoencoder flag
parser.add_argument('--VAE', type=str,\
        help='Flag VAE')
args = parser.parse_args()

# Assign GPU
os.putenv('CUDA_VISIBLE_DEVICES','{}'.format(args.GPU))

## check VAE Flag
if args.VAE == None:
    flagVAE = False
elif args.VAE.lower() == "true":
    flagVAE = True
else:
    flagVAE = False

## Clear screen (just for comfort)
os.system("clear")

## Seed for Random Number Generation
    # -- CAUTION! The seed controls how the random numbers are generated and
    #it guarantees the repeatability of the experiments
    # (generation of random shapes and initialization of the variables)
np.random.seed(seed=0)
random.seed(0)

# ==============================================================================
### Auxiliary functions
def plot3(PC, Filename, colorname='tan'):
    ''' Function to plot the point clouds as jpg/png files
    Input:
      - PC: point cloud, type: array, (-1,3)
      - Filename: name of the jpg/png file to be generated
      - colorname: name of the color of the point clouds (standard: "tan")
    Output:
      - *.jpg/png file, saved in the path described in Filename
    '''
    pltv = pv.Plotter(off_screen=True)
    pltv.set_background("white")
    pltv.add_mesh(PC, point_size=7.5, style="points", render_points_as_spheres=True,
    lighting=True, colorname='tan')
    pltv.view_isometric()
    pltv.show(screenshot=Filename)
    pltv.close()


def PC_html(PC1, PC2, figname):
    ''' Plot the point clouds as Plotly .html files
    Input:
      - PC: point cloud, type: array, (-1, 3)
      - figname: strig with the name of the output file
    Output:
      - *.html file, saved in the path described in figname
    '''
    ## Assigning the point to the corresponding variables for Plotly
    trace1 = go.Scatter3d(
        x=np.array(PC1[:,0]).flatten(),
        y=np.array(PC1[:,1]).flatten(),
        z=np.array(PC1[:,2]).flatten(),
        mode='markers',
        marker=dict(
            size=7,
            line=dict(
                color='rgb(255, 255, 255)',
                width=0.1
            ),
            opacity=0.15,
            color='rgb(255, 0, 0)',
            colorscale='Viridis'
        )
    )
    trace2 = go.Scatter3d(
        x=np.array(PC2[:,0]).flatten(),
        y=np.array(PC2[:,1]).flatten(),
        z=np.array(PC2[:,2]).flatten(),
        mode='markers',
        marker=dict(
            size=10,
            line=dict(
                color='rgb(255, 255, 255)',
                width=0.1
            ),
            opacity=1,
            color='rgb(0, 0, 255)',
            colorscale='Viridis'
        )
    )
    data = [trace1, trace2]

    ## Defining the layout of the plot (scatter 3D)
    layout = go.Layout(
        margin=dict(
            l=0,
            r=0,
            b=0,
            t=0
        ),
        autosize=True,
        scene=dict(
            camera=(dict(
                up=dict(x=0, y=0, z=1),
                center=dict(x=0, y=0, z=0),
                eye=dict(x=0.01, y=2.5, z=0.01)
            )
            ), aspectmode='data'
        )
    )
    fig = go.Figure(data=data, layout=layout)
    
    ## Plot and save figure
    plot(fig, filename=figname, auto_open=False)

# ==============================================================================
### Settings
## Name of the Experiment
name_exp = "pcae_N{}_LR{}".format(args.N, args.LR)
if flagVAE: name_exp = "v_"+name_exp

## Number of shapes to reconstruct
# - From the training set
n_shapes_trainingset = 5
# - From the test set
n_shapes_testset = 5
# - Number of steps between shapes
n_steps_interp = 5

# ==============================================================================
### Preprocessing
## Directory contatining the information about the autoencoder
top_dir = str.format(str.format("Network_{}", name_exp))
if not osp.exists(top_dir):
    print(str.format("Directory {} does not exist!", top_dir))
    exit()

# Load log dictionary with the training and network information
os.system("cp {}/log_dictionary.py .".format(top_dir))
from log_dictionary import log_dictionary
os.system("rm log_dictionary.py")

## Geometry names
geom_training = np.array(pd.read_csv(\
    "{}/geometries_training.csv".format(top_dir), header=None))
geom_testing = np.array(pd.read_csv(\
    "{}/geometries_testing.csv".format(top_dir), header=None))

## Autoencoder
# Graph information
if flagVAE: metaf = "vpcae"
else: metaf = "pcae"

pathToGraph = str.format("{}/{}", top_dir, metaf)
# - Import Graph at latest state (after training)
TFmetaFile = str.format("{}/{}.meta", top_dir, metaf)
TFDirectory = str.format("{}/", top_dir)

# ==============================================================================
### Loading the shapes
## Number of points in the point cloud
pc_size = log_dictionary["pc_size"]

## Selecting the shapes from the training and test sets
# Training set
i_shapes_training = np.array(range(geom_training.shape[0]))
i_sel_training = np.random.choice(\
    i_shapes_training.flatten(), n_shapes_trainingset, replace=False)
# Test set
i_shapes_testing = np.array(range(geom_testing.shape[0]))
i_sel_testing = np.random.choice(\
    i_shapes_testing.flatten(), n_shapes_testset, replace=False)

## Sampling point clouds
# Initialize the batch for assigning the point clouds
vis_set = np.zeros((n_shapes_trainingset+n_shapes_testset, pc_size, 3))
# Color scheme: used to differentiate the shapes in the training set (blue)
#and test set (red)
color_shape = np.zeros((n_shapes_trainingset+n_shapes_testset+1, 3))
# Log to save the id of the reconstructed shapes (initialization)
log_reconst = []
cntr = 0
# Training set
for i in i_sel_training:
    pc_load = np.array(\
        pd.read_csv(geom_training[i][0], header=None, sep=" "))[:,0:3]
    log_reconst.append(geom_training[i][0])
    if pc_load.shape[0] < pc_size:
        pc_sample = np.random.choice(\
            np.array(range(pc_load.shape[0])).flatten(), pc_size)
    else:
        pc_sample = np.random.choice(\
            np.array(range(pc_load.shape[0])).flatten(), pc_size, replace=False)
    color_shape[cntr,2] = 1
    vis_set[cntr,:,:] = pc_load[pc_sample,:]
    cntr = cntr+1
# Test set
for i in i_sel_testing:
    log_reconst.append(geom_testing[i][0])
    pc_load = np.array(\
        pd.read_csv(geom_testing[i][0], header=None, delimiter=" "))[:,0:3]
    if pc_load.shape[0] < pc_size:
        pc_sample = np.random.choice(\
            np.array(range(pc_load.shape[0])).flatten(), pc_size)
    else:
        pc_sample = np.random.choice(\
            np.array(range(pc_load.shape[0])).flatten(), pc_size, replace=False)
    color_shape[cntr, 0] = 1
    vis_set[cntr,:,:] = pc_load[pc_sample,:]
    cntr = cntr+1
vis_set[-1,:,:] = pc_load[pc_sample,:]
color_shape[-1, 2] = 1

## Normalize the set of geometries
# Load point cloud normalization values
normDS = np.array(pd.read_csv(str.format("{}/normvalues.csv", top_dir),\
    header=None)).flatten()
maX = normDS[0]
miX = normDS[1]
Delta = maX - miX
# Normalize the data
vis_set,_ = data_set_norm(vis_set, np.array([0.1, 0.9]), \
        inp_lim=np.array([miX, maX]))

# Log the name of the geometries used for plotting (for verification)
pd.DataFrame(log_reconst).to_csv(str.format(\
    "{}/geometries_reconstruction.csv", top_dir), header=None, index=None)

# ==============================================================================
### Visualizing point clouds
## Create directory to save the files
dir_pc_plot = str.format("{}/point_cloud_interpolation", top_dir)
os.system(str.format("mkdir {}", dir_pc_plot))

## Start session
with tf.Session() as sess:
    # import graph data
    new_saver = tf.train.import_meta_graph(TFmetaFile, clear_devices=True)
    new_saver.restore(sess, tf.train.latest_checkpoint(TFDirectory))
    graph = tf.get_default_graph()
    #print(tf.global_variables())
    #exit()
    # import network main layers
    # - Input
    x = graph.get_tensor_by_name("x:0")
    # - Latent Representation
    latent_rep = graph.get_tensor_by_name("latent_rep:0")
    # - Point clouds
    point_clouds = graph.get_tensor_by_name("PC:0")
    if flagVAE: dpout = graph.get_tensor_by_name("do_rate:0")

    ## Latent representation for all input point clouds
    if flagVAE:
        latent_rep_total = sess.run(latent_rep, \
            feed_dict={x: vis_set, dpout: 1.0})
    else:
        latent_rep_total = sess.run(latent_rep, feed_dict={x: vis_set})
    # Add initial 
    latent_rep_total = np.concatenate((latent_rep_total, np.reshape(\
        latent_rep_total[0,:,:], (1,-1, 1))), axis=0)
    latent_rep_size = latent_rep_total.shape[1]

    ## Interpolate and plot
    # Rotation angle
    ar_range = 180
    cntr = 0
    n_shapes = vis_set.shape[0]
    for i in range(n_shapes):
        
        for j in range(n_steps_interp):
            ## Interpolated latent representation
            shp_interp = latent_rep_total[i,:,:]*(1-np.float(j)/\
                (n_steps_interp-1))+\
                latent_rep_total[i+1,:,:]*(np.float(j)/(n_steps_interp-1))
            latent_interp = np.reshape(shp_interp, (1,latent_rep_size,1))
            ## Interpolated color
            col_interp = 0.5*(\
                color_shape[i,:]*(1-np.float(j)/(n_steps_interp-1))+\
                color_shape[i+1,:]*(np.float(j)/(n_steps_interp-1))\
                   )

            ## Retrieve the point Cartesian coordinates using the trained model
            if flagVAE:
                pc_interpolated = np.reshape(sess.run(point_clouds, \
                    feed_dict={latent_rep: latent_interp, dpout: 1.0}), (-1, 3))
            else:
                pc_interpolated = np.reshape(sess.run(point_clouds, \
                    feed_dict={latent_rep: latent_interp}), (-1, 3))

            ## Plot the point cloud
            # HTML representation (initial shape)
            if j == 0 : 
                # - HTML filename
                html_name = \
                    "{}/PC_{}_reconstruction.html".format(dir_pc_plot, i)
                # - Plot
                PC_html(vis_set[i,:,:], pc_interpolated, html_name)
            # PNG file for animation
            # - PNG filename
            pc_name = "{}/PC_{}_{}.png".format(\
                dir_pc_plot, str(i).zfill(5),str(j).zfill(3)   
            )
            # - azimuthal angle
            az = (90-ar_range/2) + (cntr/(n_shapes*n_steps_interp))*ar_range
            cntr = cntr + 1
            # - Plot
            plot3(pc_interpolated, pc_name, az=az, col=col_interp)

    # Generate GIF animation
    os.system(str.format("convert -delay 40 -loop 0 {}/*.png \
        {}/interpolation.gif", dir_pc_plot, dir_pc_plot))

exit()
