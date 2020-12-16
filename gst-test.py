#!python3

import numpy as np
import cv2
import os
import json
import time
import platform
import gi

gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

Gst.debug_set_active(True)
Gst.debug_set_default_threshold(4)

GObject.threads_init()

Gst.init(None)
mainloop = GObject.MainLoop()

def on_bus_message(message):
    print("on_bus_message")
    t = message.type
    if t == Gst.MessageType.EOS:
        print("Eos")
    elif t == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        print('Warning: %s: %s\n' % (err, debug))
        #sys.stderr.write('Warning: %s: %s\n' % (err, debug))
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print('Error: %s: %s\n' % (err, debug))
        #sys.stderr.write('Error: %s: %s\n' % (err, debug))   

RTMP_SERVER = "rtmp://localhost:1935/live/"

#MACOS
#CLI='flvmux name=mux streamable=true ! rtmp2sink location="'+ RTMP_SERVER +'" sync=true \
#    videotestsrc do-timestamp=TRUE is-live=TRUE ! videoconvert ! vtenc_h264 ! video/x-h264 ! h264parse ! video/x-h264 ! \
#    queue max-size-buffers=0 max-size-bytes=0 max-size-time=134000000 min-threshold-buffers=1 leaky=upstream ! mux. \
#    osxaudiosrc device=87 do-timestamp=true ! audioconvert ! audioresample ! audio/x-raw, format=S16LE, rate=44100, channels=1, channel-mask=(bitmask)0x1 ! faac bitrate=48000 ! audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! \
#    queue max-size-buffers=0 max-size-bytes=0 max-size-time=670000000 min-threshold-buffers=1 ! mux.'

#RPI
CLI='flvmux name=mux streamable=true latency=3000000000 ! rtmpsink location="'+ RTMP_SERVER +' live=1 flashver=FME/3.0%20(compatible;%20FMSc%201.0)"  \
	videotestsrc ! video/x-raw,width=640,height=480,framerate=15/1 ! videoconvert !  omxh264enc ! video/x-h264 ! h264parse ! video/x-h264 ! \
	queue max-size-buffers=0 max-size-bytes=0 max-size-time=180000000 min-threshold-buffers=1 leaky=upstream ! mux. \
	alsasrc ! audio/x-raw, format=S16LE, rate=44100, channels=1 ! voaacenc bitrate=44100 !  audio/mpeg ! aacparse ! audio/mpeg, mpegversion=4 ! \
    queue max-size-buffers=0 max-size-bytes=0 max-size-time=4000000000 min-threshold-buffers=1 ! mux.'

print( CLI )

pipe=Gst.parse_launch(CLI)

#appsrc=pipe.get_by_name("mysource")

#appsrc.set_property('emit-signals',True) #tell sink to emit signals

# Set up a pipeline bus watch to catch errors.
bus = pipe.get_bus()
bus.connect("message", on_bus_message)

pipe.set_state(Gst.State.PLAYING)
mainloop.run()
