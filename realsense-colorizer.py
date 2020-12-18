## License: Apache 2.0. See LICENSE file in root directory.
## Copyright(c) 2015-2017 Intel Corporation. All Rights Reserved.

###############################################
##      Open CV and Numpy integration        ##
###############################################

import pyrealsense2 as rs
import os
import json
import time
import sys
import platform
import asyncio
import numpy as np
import cv2
from timeit import default_timer as timer

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

Gst.init(None)
#Gst.debug_set_active(True)
#Gst.debug_set_default_threshold(4)

rtmp_url = "rtmp://global-live.mux.com:5222/app/24b131aa-2712-49cb-9035-78013d501544"
width = 640
height = 480

CLI = ''
caps =  'caps="video/x-raw,format=BGR,width='+str(width)+',height='+ str(height*2) + ',framerate=(fraction)30/1,pixel-aspect-ratio=(fraction)1/1"'

if platform.system() == "Linux":
    #assuming Linux means RPI
    
    CLI='flvmux name=mux streamable=true latency=3000000000 ! rtmpsink location="'+  rtmp_url +' live=1 flashver=FME/3.0%20(compatible;%20FMSc%201.0)" \
        appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE '+ str(caps) +' ! \
        videoconvert !  omxh264enc ! video/x-h264 ! h264parse ! video/x-h264 ! \
        queue max-size-buffers=0 max-size-bytes=0 max-size-time=180000000 min-threshold-buffers=1 leaky=upstream ! mux. \
        alsasrc ! audio/x-raw, format=S16LE, rate=44100, channels=1 ! voaacenc bitrate=44100 !  audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! \
        queue max-size-buffers=0 max-size-bytes=0 max-size-time=4000000000 min-threshold-buffers=1 ! mux.'

elif platform.system() == "Darwin":
    #macos
    #CLI='flvmux name=mux streamable=true ! rtmpsink location="'+  rtmp_url +' live=1 flashver=FME/3.0%20(compatible;%20FMSc%201.0)" \
    #    appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE '+ str(caps) +' ! \
    #    videoconvert ! vtenc_h264 ! video/x-h264 ! h264parse ! video/x-h264 ! \
    #    queue max-size-buffers=4 ! flvmux name=mux. \
    #    osxaudiosrc do-timestamp=true ! audioconvert ! audioresample ! audio/x-raw,rate=48000 ! faac bitrate=48000 ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! \
    #    queue max-size-buffers=4 ! mux.'

    CLI='appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE caps="video/x-raw,format=BGR,width='+str(width)+',height='+ str(height*2) + ',framerate=(fraction)30/1,pixel-aspect-ratio=(fraction)1/1" ! videoconvert ! vtenc_h264 ! video/x-h264 ! h264parse ! video/x-h264 ! queue max-size-buffers=4 ! flvmux name=mux ! rtmpsink location="'+ rtmp_url +'" sync=true   osxaudiosrc do-timestamp=true ! audioconvert ! audioresample ! audio/x-raw,rate=48000 ! faac bitrate=48000 ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! queue max-size-buffers=4 ! mux.' 


#TODO: windows

print( CLI )
gstpipe=Gst.parse_launch(CLI)

appsrc=gstpipe.get_by_name("mysource")
appsrc.set_property('emit-signals',True) #tell sink to emit signals

gstpipe.set_state(Gst.State.PLAYING)


# Configure depth and color streams
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

# Start streaming
profile = pipeline.start(config)

align_to = rs.stream.depth
align = rs.align(align_to)

min_depth = 0.1
max_depth = 4.0

# Create colorizer object
colorizer = rs.colorizer()
colorizer.set_option(rs.option.color_scheme, 9)
colorizer.set_option(rs.option.histogram_equalization_enabled,0)
colorizer.set_option(rs.option.min_distance, min_depth)
colorizer.set_option(rs.option.max_distance, max_depth)
# Filter
thr_filter = rs.threshold_filter()
thr_filter.set_option(rs.option.min_distance, min_depth)
thr_filter.set_option(rs.option.max_distance, max_depth)

# Disparity
dp_filter = rs.disparity_transform()

#https://dev.intelrealsense.com/docs/depth-image-compression-by-colorization-for-intel-realsense-depth-cameras#section-6references
#https://github.com/TetsuriSonoda/rs-colorize/blob/master/rs-colorize/rs-colorize.cpp

start = timer()
cv2.namedWindow('RealSense', cv2.WINDOW_AUTOSIZE)
cv2.moveWindow("RealSense", 0,0)

depth_sensor = profile.get_device().first_depth_sensor()

intrinsics = True
try:
    while True:

        # Wait for a coherent pair of frames: depth and color
        frames = pipeline.wait_for_frames()
        frames = align.process(frames)

        end = timer()
        rl_wait = end - start
        start = timer()
        
        # Align the depth frame to color frame
        #aligned_frames = align.process(frames)

        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()
        if not depth_frame or not color_frame:
            continue

        if( intrinsics):

            depth_units = depth_sensor.get_option(rs.option.depth_units)
            stereo_baseline_meter = depth_sensor.get_option(rs.option.stereo_baseline) * depth_units

            depth_intrinsics = depth_frame.profile.as_video_stream_profile().intrinsics

            _focal_lenght_mm = depth_intrinsics.fx

            #The disparity unit is in 1/32 pixels, so 4000 would be roughly equal to 125 pixels.
            fractional_bits = 5
            fractions = 1 << fractional_bits
            _d2d_convert_factor = (stereo_baseline_meter * _focal_lenght_mm * fractions) / depth_units

            min_disparity = _d2d_convert_factor / max_depth
            max_disparity = _d2d_convert_factor / min_depth

            print("Intel Realsense Camera Intrinsics: ")
            print("========================================")
            print(depth_frame.profile.as_video_stream_profile().intrinsics)
            print('_d2d_convert_factor:{0} min_disparity:{1} max_disparity:{2} baseline:{3} scale:{4}, fractions{5}'.format(_d2d_convert_factor,min_disparity,max_disparity, stereo_baseline_meter, depth_units, fractions ))
            print("")

            intrinsics = False

        # Convert images to numpy arrays
        #depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        end = timer()
        rl_frame = end - start
        start = timer()

        filtered = thr_filter.process(depth_frame)

        #disparity filter
        #filtered = dp_filter.process(filtered)
        
        end = timer()
        rl_dpfilter = end - start
        start = timer()


        # Colorize depth frame to jet colormap
        depth_color_frame = colorizer.colorize(filtered)

        # Convert depth_frame to numpy array to render image in opencv
        depth_color_image = np.asanyarray(depth_color_frame.get_data())


        end = timer()
        rl_colorize = end - start
        start = timer()

        # Stack both images horizontally
        images = np.vstack((color_image, depth_color_image))

        end = timer()
        cv_stack = end - start
        start = timer()


        # ffplay -f avfoundation -i "2:0" -vf  "crop=1024:768:400:800" -pix_fmt yuv420p -y 

        # push to gstreamer
        frame = images.tostring()
        buf = Gst.Buffer.new_allocate(None, len(frame), None)
        buf.fill(0,frame)
        appsrc.emit("push-buffer", buf)


        end = timer()
        gst = end - start
        start = timer()


        # Show images
        cv2.imshow('RealSense', images)

        end = timer()
        cvwait = end - start
        start = timer()

        total = rl_frame+rl_dpfilter+rl_colorize+cv_stack+gst+cvwait

        #print('wait:{0:.4f},frame:{1:.4f},filter:{2:.4f},color:{3:.4f},stack:{4:.4f},send:{5:.4f},show:{6:.4f},total{7:.4f}'.format( rl_wait*1000, rl_frame*1000, rl_dpfilter*1000, rl_colorize*1000, cv_stack*1000,gst*1000,cvwait*1000, total*1000) )
        cv2.waitKey(1)

finally:

    # Stop streaming
    pipeline.stop()