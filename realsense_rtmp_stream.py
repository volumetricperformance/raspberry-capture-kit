#!python3
try:
	import pyrealsense2.pyrealsense2 as rs
except ModuleNotFoundError:
	import pyrealsense2 as rs

import numpy as np
import cv2
import os
import json
import time
import sys
import platform
import asyncio
from timeit import default_timer as timer

import multiprocessing.queues as mpq
from multiprocessing import Process, Queue
import multiprocessing as mp
from gstreamer_sender import GStreamerSender

from flask import Flask, Response, render_template, send_from_directory
from flask_socketio import SocketIO, emit

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst
import traceback


#workaround for running this on macos
#https://stackoverflow.com/a/24941654
#https://stackoverflow.com/q/39496554
class XQueue(mpq.Queue):

    def __init__(self,*args,**kwargs):
        ctx = mp.get_context()
        super(XQueue, self).__init__(*args, **kwargs, ctx=ctx)

    def empty(self):
        try:
            return self.qsize() == 0
        except NotImplementedError:  # OS X -- see qsize() implementation
            return super(XQueue, self).empty()

class RealsenseCapture (mp.Process):

    def __init__(self, rtmp_uri, config_json, w, h, statusQueue, messageQueue, gststream):
        mp.Process.__init__(self)

        self.exit = mp.Event()
        self.rtmp_url = rtmp_uri
        self.json_file = config_json
        self.width = w
        self.height = h
        self.statusQueue = statusQueue
        self.messageQueue = messageQueue
        self.gststream = gststream
        self.rspipeline = None
        self.framecount = 0

        print ("Initialized Realsense Capture")

    def shutdown(self):
        print ("Shutdown Realsense Capture")
        self.exit.set()

    def loadConfiguration(self,profile, json_file):
        dev = profile.get_device()
        advnc_mode = rs.rs400_advanced_mode(dev)
        print("Advanced mode is", "enabled" if advnc_mode.is_enabled() else "disabled")
        json_obj = json.load(open(json_file))
        json_string = str(json_obj).replace("'", '\"')
        advnc_mode.load_json(json_string)

        while not advnc_mode.is_enabled():
            print("Trying to enable advanced mode...")
            advnc_mode.toggle_advanced_mode(True)

            # At this point the device will disconnect and re-connect.
            print("Sleeping for 5 seconds...")
            time.sleep(5)

            # The 'dev' object will become invalid and we need to initialize it again
            dev = profile.get_device()
            advnc_mode = rs.rs400_advanced_mode(dev)
            print("Advanced mode is", "enabled" if advnc_mode.is_enabled() else "disabled")
            advnc_mode.load_json(json_string)

    def spatial_filtering(self,depth_frame, magnitude=2, alpha=0.5, delta=20, holes_fill=0):
        spatial = rs.spatial_filter()
        spatial.set_option(rs.option.filter_magnitude, magnitude)
        spatial.set_option(rs.option.filter_smooth_alpha, alpha)
        spatial.set_option(rs.option.filter_smooth_delta, delta)
        spatial.set_option(rs.option.holes_fill, holes_fill)
        depth_frame = spatial.process(depth_frame)
        return depth_frame

    def hole_filling(self,depth_frame):
        hole_filling = rs.hole_filling_filter()
        depth_frame = hole_filling.process(depth_frame)
        return depth_frame

    def run(self):
        # ========================
        # 1. Configure all streams
        # ========================
        self.rspipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, 30)
        config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, 30)

        # ======================
        # 2. Start the streaming
        # ======================
        print("Starting up the Intel Realsense...")
        print("")
        profile = self.rspipeline.start(config)

        # Load the configuration here
        self.loadConfiguration(profile, self.json_file)

        # =================================
        # 3. The depth sensor's depth scale
        # =================================
        depth_sensor = profile.get_device().first_depth_sensor()
        depth_scale = depth_sensor.get_depth_scale()
        print("Depth Scale is: ", depth_scale)
        print("")

        # ==========================================
        # 4. Create an align object.
        #    Align the depth image to the rgb image.
        # ==========================================
        align_to = rs.stream.depth
        align = rs.align(align_to)

        try:
            # ===========================================
            # 5. Skip the first 30 frames.
            # This gives the Auto-Exposure time to adjust
            # ===========================================
            for x in range(30):
                frames = self.rspipeline.wait_for_frames()
                # Align the depth frame to color frame
                aligned_frames = align.process(frames)

            print("Intel Realsense started successfully.")
            print("")

            #self.gstreamer = GStreamerSender(self.rtmp_url, self.width, self.height, self.statusQueue, self.messageQueue)
            #print("initialized")
            #self.gstreamer.start()

            intrinsics = True
            depth_hsv = np.zeros((480, 640, 3), dtype=np.float32)

            start = timer()
            
            while not self.exit.is_set():
                # ======================================
                # 7. Wait for a coherent pair of frames:
                # ======================================
                frames = self.rspipeline.wait_for_frames()

                # =======================================
                # 8. Align the depth frame to color frame
                # =======================================
                aligned_frames = align.process(frames)
                
                waitFrameTime = timer()
                #print(str(waitFrameTime-start) + " rl align time")
                

                # ================================================
                # 9. Fetch the depth and colour frames from stream
                # ================================================
                depth_frame = aligned_frames.get_depth_frame()
                color_frame = aligned_frames.get_color_frame()
                if not depth_frame or not color_frame:
                    pass
                
                # print the camera intrinsics just once. it is always the same
                if intrinsics:
                    print("Intel Realsense Camera Intrinsics: ")
                    print("========================================")
                    print(depth_frame.profile.as_video_stream_profile().intrinsics)
                    print(color_frame.profile.as_video_stream_profile().intrinsics)
                    print("")
                    intrinsics = False

                # =====================================
                # 10. Apply filtering to the depth image
                # =====================================
                # Apply a spatial filter without hole_filling (i.e. holes_fill=0)
                # depth_frame = self.spatial_filtering(depth_frame, magnitude=2, alpha=0.5, delta=10, holes_fill=1)
                # Apply hole filling filter
                # depth_frame = self.hole_filling(depth_frame)

                # ==================================
                # 11. Convert images to numpy arrays
                # ==================================
                depth_image = np.asanyarray(depth_frame.get_data()).astype( np.float32)
                color_image = np.asanyarray(color_frame.get_data())
                
                #print(str(timer() - waitFrameTime) + " rl frame time")
                
                
                #color is nparray of rl color, depth is nparray of rl depth

                # We need to encode/pack the 16bit depth value to RGB
                # we do this by treating it as the Hue in HSV. 
                # we then encode HSV to RGB and stream that
                # on the other end we reverse RGB to HSV, H will give us the depth value back.
                # HSV elements are in the 0-1 range so we need to normalize the depth array to 0-1
                # First set a far plane and set everything beyond that to 0

                clipped = depth_image > 4000
                depth_image[clipped] = 0

                # Now normalize using that far plane
                # cv expects the H in degrees, not 0-1 :(
                depth_image *= (360/4000)
                depth_hsv[:,:,0] = depth_image
                depth_hsv[:,:,1] = 1
                depth_hsv[:,:,2] = 1
                discard = depth_image == 0
                s = depth_hsv[:,:,1]
                v = depth_hsv[:,:,2] 
                s[ discard] = 0
                v[ discard] = 0

                # cv2.cvtColor to convert HSV to RGB
                hsv = cv2.cvtColor(depth_hsv, cv2.COLOR_HSV2BGR_FULL)

                # cv2 needs hsv to 8bit (0-255) to stack with the color image
                hsv8 = (hsv*255).astype( np.uint8)
                

                if(not self.exit.is_set()):
                    try:
                        if(not self.messageQueue.full()):
                            self.messageQueue.put_nowait((color_image, hsv8))
                    except:
                        pass
                    
                frameTimer = timer()
                print("realsense frame: %s" % str(1/(frameTimer-start)))
                start = timer()

        except:        
            e = sys.exc_info()[0]
            print( "Unexpected Error: %s" % e )
            self.statusQueue.put_nowait("ERROR: Realsense Unexpected Error: %s" % e)
            self.exit.set()

        finally:
            # Stop streaming
            print( "Stop realsense pipeline" )
            self.rspipeline.stop()
        
        self.statusQueue.put_nowait("INFO: Exiting Realsense process")
        print ("Exiting realsense process")
