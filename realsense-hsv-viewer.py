## License: Apache 2.0. See LICENSE file in root directory.
## Copyright(c) 2015-2017 Intel Corporation. All Rights Reserved.

###############################################
##      Open CV and Numpy integration        ##
###############################################
try:
        import pyrealsense2.pyrealsense2 as rs
except ModuleNotFoundError:
        print('Use local realsense lib')
        import pyrealsense2 as rs

import numpy as np
import cv2
import platform
from timeit import default_timer as timer

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstBase', '1.0')
from gi.repository import GObject, Gst, GstBase

Gst.init(None)
#Gst.debug_set_active(True)
#Gst.debug_set_default_threshold(4)

sink = "test-hsv.mp4"
width = 640
height = 480

CLI = ''
caps =  'caps="video/x-raw,format=BGR,width='+str(width)+',height='+ str(height*2) + ',framerate=(fraction)30/1,pixel-aspect-ratio=(fraction)1/1"'

if platform.system() == "Linux":
    #assuming Linux means RPI
    
    #rtmp
    #CLI='flvmux name=mux streamable=true latency=3000000000 ! rtmpsink location="'+  sink +' live=1 flashver=FME/3.0%20(compatible;%20FMSc%201.0)" \
    #    appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE '+ str(caps) +' ! \
    #    videoconvert !  omxh264enc ! video/x-h264 ! h264parse ! video/x-h264 ! \
    #    queue max-size-buffers=0 max-size-bytes=0 max-size-time=180000000 min-threshold-buffers=1 leaky=upstream ! mux. \
    #    alsasrc ! audio/x-raw, format=S16LE, rate=44100, channels=1 ! voaacenc bitrate=44100 !  audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! \
    #    queue max-size-buffers=0 max-size-bytes=0 max-size-time=4000000000 min-threshold-buffers=1 ! mux.'

    #mp4
    CLI='qtmux name=mux streamable=true ! filesink location="'+  sink +'" \
        appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE '+ str(caps) +' ! \
        videoconvert ! omxh264enc ! h264parse ! video/x-h264 ! \
        queue ! mux.video_0 \
        alsasrc ! audio/x-raw, format=S16LE, rate=44100, channels=1 ! voaacenc bitrate=44100 !  audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! \
        queue max-size-buffers=0 max-size-bytes=0 max-size-time=4000000000 min-threshold-buffers=1 ! mux.audio_0'

elif platform.system() == "Darwin":
    #macos

    #stream to rtmp
    #CLI='flvmux name=mux streamable=true ! rtmpsink location="'+  sink +' live=1 flashver=FME/3.0%20(compatible;%20FMSc%201.0)" \
    #    appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE '+ str(caps) +' ! \
    #    videoconvert ! vtenc_h264 ! video/x-h264 ! h264parse ! video/x-h264 ! \
    #    queue max-size-buffers=4 ! flvmux name=mux. \
    #    osxaudiosrc do-timestamp=true ! audioconvert ! audioresample ! audio/x-raw,rate=48000 ! faac bitrate=48000 ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! \
    #    queue max-size-buffers=4 ! mux.'

    #CLI='appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE caps="video/x-raw,format=BGR,width='+str(width)+',height='+ str(height*2) + ',framerate=(fraction)30/1,pixel-aspect-ratio=(fraction)1/1" ! videoconvert ! vtenc_h264 ! video/x-h264 ! h264parse ! video/x-h264 ! queue max-size-buffers=4 ! flvmux name=mux ! rtmpsink location="'+ sink +'" sync=true   osxaudiosrc do-timestamp=true ! audioconvert ! audioresample ! audio/x-raw,rate=48000 ! faac bitrate=48000 ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! queue max-size-buffers=4 ! mux.' 

    #save to webm (does not work on rpi)
    #CLI='webmmux name=mux ! filesink location="'+  sink +'" \
    #    appsrc name=mysource format=TIME do-timestamp=TRUE is-live=TRUE '+ str(caps) +' ! \
    #    videoconvert ! vp8enc ! queue ! \
    #    mux.video_0 \
    #    osxaudiosrc do-timestamp=true ! audioconvert ! vorbisenc ! \
    #    queue max-size-buffers=4 ! mux.audio_0'

    #save to mp4
    CLI='mp4mux name=mux streamable=true ! filesink location="'+  sink +'" \
        appsrc name=mysource format=TIME do-timestamp=true is-live=true '+ str(caps) +' ! \
        videoconvert ! vtenc_h264_hw ! h264parse ! video/x-h264 ! queue ! \
        mux.video_0 \
        osxaudiosrc do-timestamp=true ! audioconvert ! avenc_aac ! aacparse ! queue ! \
        mux.audio_0' 

#TODO: windows

print( CLI )
gstpipe=Gst.parse_launch(CLI)

appsrc=gstpipe.get_by_name("mysource")
appsrc.set_property('emit-signals',True) #tell sink to emit signals

#NOTE: this only applies for mp4, not rtmp!
if platform.system() == "Linux":
    #on rpi with older version of gstreamer 1.4 we get "gst_qt_mux_add_buffer: error: Buffer has no PTS."
    #this is the fix
    #https://stackoverflow.com/questions/42874691/gstreamer-for-android-buffer-has-no-pts
    #https://gist.github.com/zougloub/0747f84d45bc35413c0c19584c398b3d#file-dvr-py-L83
    it0 = gstpipe.iterate_elements()
    while True:
        res0, e = it0.next()
        
        if e is None:
            break

        if e.name == "h264parse0":
            #Workaround  PTS issue            
            GstBase.BaseParse.set_infer_ts(e, True)
            GstBase.BaseParse.set_pts_interpolation(e, True)

gstpipe.set_state(Gst.State.PLAYING)


# Configure depth and color streams
config = rs.config()
#rs.config.enable_device_from_file(config, "20210102_083625.bag")

pipeline = rs.pipeline()

config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

colorizer = rs.colorizer()
colorizer.set_option(rs.option.color_scheme, 0)


# Start streaming
pipeline.start(config)

align_to = rs.stream.depth
align = rs.align(align_to)
depth_hsv = np.zeros((480, 640, 3), dtype=np.float32)

running = True

try:
    while running:
        start = timer()
        framestart = timer()
        # Wait for a coherent pair of frames: depth and color
        frames = pipeline.wait_for_frames()
        frameWaitTime = timer() - start
        print(str(frameWaitTime) + " frame wait time")
        
        # Align the depth frame to color frame
        start = timer()
        aligned_frames = align.process(frames)

        depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()
        syncedFrameTime = timer() - start
        print(str(syncedFrameTime) + " synced time")

        if not depth_frame or not color_frame:
            continue

        # Convert images to numpy arrays
        start = timer()
        depth_image = np.asanyarray(depth_frame.get_data()).astype( np.float32)
        color_image = np.asanyarray(color_frame.get_data())
        frameToNpTime = timer() - start
        print(str(frameToNpTime) + " numpy array time")

        # We need to encode/pack the 16bit depth value to RGB
        # we do this by treating it as the Hue in HSV. 
        # we then encode HSV to RGB and stream that
        # on the other end we reverse RGB to HSV, H will give us the depth value back.
        # HSV elements are in the 0-1 range so we need to normalize the depth array to 0-1
        # First set a far plane and set everything beyond that to 0
        
        start = timer()
        clipped = depth_image > 4000
        depth_image[clipped] = 0
        hsvTimer = timer()
        print(str(hsvTimer - start) + " clip")

        # Now normalize using that far plane
        # cv expects the H in degrees, not 0-1 :(
        start = timer()
        depth_image *= (360/4000)

        hsvTimer = timer()
        print(str(hsvTimer - start) + " depth_image_norm")

        start = timer()
        depth_hsv[:,:,0] = depth_image
        depth_hsv[:,:,1] = 1
        depth_hsv[:,:,2] = 1
        hsvTimer = timer()
        print(str(hsvTimer - start) + " depth_concat")

        start = timer()
        discard = depth_image == 0
        s = depth_hsv[:,:,1]
        v = depth_hsv[:,:,2] 
        s[ discard] = 0
        v[ discard] = 0
        hsvTimer = timer()
        print(str(hsvTimer - start) + " s v discard")

        # cv2.cvtColor to convert HSV to RGB
        start = timer()
        hsv = cv2.cvtColor(depth_hsv, cv2.COLOR_HSV2BGR_FULL)

        # cv2 needs hsv to 8bit (0-255) to stack with the color image
        hsv8 = (hsv*255).astype( np.uint8)
        hsvTime = timer()
        print(str(hsvTime-start) + " hsv conversion time")

        # Stack both images horizontally
        start = timer()
        images = np.vstack((color_image, hsv8))       
        stackTime = timer()
        print(str(stackTime-start) + " stack time")

         # push to gstreamer
        start = timer()
        frame = images.tostring()
        buf = Gst.Buffer.new_allocate(None, len(frame), None)
        buf.fill(0,frame)
        appsrc.emit("push-buffer", buf)
        gstBufTime = timer()
        print(str(gstBufTime-start) + " gst buffer time")

        # Show images
        cv2.imshow('RealSense', images)
        windowTime = timer()
        print(str(windowTime-start) + " stack and show time")
        print(str(timer()-framestart) + " total time")

        if cv2.waitKey(1) == 27:
            running = False

finally:
    appsrc.emit("end-of-stream")

    print("Sending an EOS event to the pipeline")
    gstpipe.send_event(Gst.Event.new_eos())
    print("Waiting for the EOS message on the bus")
    bus = gstpipe.get_bus()
    bus.timed_pop_filtered(Gst.CLOCK_TIME_NONE, Gst.MessageType.EOS)
    print("Stopping pipeline")
    gstpipe.set_state(Gst.State.NULL) 

    print("Stopping realsense")
    # Stop streaming
    pipeline.stop()
