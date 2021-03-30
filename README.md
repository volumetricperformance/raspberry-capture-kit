# Realsense to RTMP streaming pipeline

This program can run on MacOS/Ubuntu/Raspbian. Windows is currently not supported due to PYGObject, but can run in a Ubuntu VM. See [Ubuntu Install](#Ubuntu-Install) for instructions. Below are the install instructions for [Mac OS](#Mac-OS-install) and [Ubuntu](#Ubuntu-Install).

### To install realsense SDK on a raspberry pi:

https://github.com/IntelRealSense/librealsense/blob/master/doc/installation_raspbian.md

### To clone, compile, and install opencv on a raspberry pi:

https://www.learnopencv.com/install-opencv-4-on-raspberry-pi/


### To install gstreamer

https://gist.github.com/neilyoung/8216c6cf0c7b69e25a152fde1c022a5d

### Inatall gstreamer python bindings

https://docs.mopidy.com/en/v0.8.0/installation/gstreamer/

### LCD Driver (Optional)

https://www.amazon.com/gp/product/B07WQW6H9S


# Mac OS install
Install homebrew, follow the steps from [here](https://brew.sh/). Make sure that xcode is installed and up to date before proceeding.

Install [Python 3.6.8](https://www.python.org/downloads/release/python-368/). This is the version that is verified to work, but it may work with other version of Python.

## Install PyGObject and dependencies

Install PyGObject by following the steps [here](https://pygobject.readthedocs.io/en/latest/getting_started.html). If you're using a Python version manager like pyenv, follow the instructions [here](We recommend following the instructions to create a development environment with PyGObject to make it easier to work with Python 3.6.8: [https://pygobject.readthedocs.io/en/latest/devguide/dev_environ.html](https://pygobject.readthedocs.io/en/latest/devguide/dev_environ.html) next. Homebrew might be able to install it as well with `brew install pygobject3 gtk+3`.

Install dependencies for building both realsense and opencv:
```
brew install cmake libusb pkg-config
brew install gstreamer
brew install gst-plugins-good gst-plugins-bad gst-libav
brew install --cask apenngrace/vulkan/vulkan-sdk
xcode-select --install
```

## Installing Intel Realsense SDK
Download librealsense: `git clone https://github.com/IntelRealSense/librealsense.git`

Follow the guide on Intel Realsense's [github](https://github.com/IntelRealSense/librealsense/blob/master/doc/installation_osx.md) up until the final cmake command (Step 4). Use the command below instead to build realsense for Python 3.6.8.
```
sudo cmake .. \
-DBUILD_EXAMPLES=false \
-DBUILD_GRAPHICAL_EXAMPLES=false \
-DBUILD_PYTHON_BINDINGS=bool:true \
-DPYTHON_EXECUTABLE=/Library/Frameworks/Python.framework/Versions/3.6/bin/python3.6

sudo make -j2
sudo make install
```
After `sudo make install` has finished, note the paths to the files `pyrealsense2.cpython-36m-darwin.so` and `pybackend2.cpython-36m-darwin.so` in your terminal window's output. These may look something like `/Library/Python/3.8/site-packages/pyrealsense2/pyrealsense2.cpython-36m-darwin.so`. You will need these paths in the next section.

## Setting up the raspberry-capture-kit repo
```
git clone https://github.com/volumetricperformance/raspberry-capture-kit.git
cd raspberry-capture-kit
git fetch
git checkout release
```
Continue from here with the two file paths you noted in the previous step.
```
cp /PATH/TO/site-packages/pyrealsense2/pyrealsense2.cpython-36m-darwin.so pyrealsense2.so
cp /PATH/TO/site-packages/pyrealsense2/pybackend2.cpython-36m-darwin.so pybackend2.so
python3.6 -m pip install virtualenv
python3.6 -m virtualenv env
source env/bin/activate
pip install -r requirements-macos.txt
```

## Installing OpenCV
With the virtual environment active in the repo directory cloned in the previous section, run the command `pip install opencv-contrib-python`.

## Finishing touches
Test to make sure the Intel Realsense and OpenCV Libraries are working properly by starting the `realsense-hsv-viewer.py` program with the camera connected. It should open a window and show a preview of the Realsense camera.

# Ubuntu Install
This was tested and verrified on Ubuntu 20.04 LTS, but should work on many Ubuntu versions. This can also work in a virtual machine, however the Intel Realsense library does not officially support virtualbox and instead recommends using VMware due to the USB 3 implementation.

## Install dependencies
```
sudo apt update
sudo apt install git cmake
sudo apt-get install build-essential python3-dev  libsqlite3-dev libgdbm-dev zlib1g-dev libbz2-dev sqlite3 tk-dev zip libssl-dev liblzma-dev libreadline-dev libffi-dev
sudo apt install libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-3.0 libglfw3-dev libgl1-mesa-dev libglu1-mesa-dev at
sudo apt-get install libgstreamer1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-doc gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 gstreamer1.0-pulseaudio
```

## Install Python3.6.8
Loosely following the guide [here](https://qiita.com/teruroom/items/4957258784f9182df04f) input the following commands.
```
wget https://www.python.org/ftp/python/3.6.8/Python-3.6.8.tgz
tar xf Python-3.6.8.tgz
cd Python-3.6.8
./configure --enable-optimizations --prefix=/opt/python3.6.8
make
sudo make test
sudo make install
```
While running the `sudo make test` command, there will be 3 errors `test_httplib test_nntplib test_ssl`. Everything will still work as intended regardless.

Type in this command `sudo ln /opt/python3.6.8/bin/python3.6 /usr/local/bin/python3.6` to make it easier to run python3.6 from the terminal

## Install Realsense
Follow the Intel Realsense [guide](https://github.com/IntelRealSense/librealsense/blob/master/doc/installation.md) up intil the cmake step (Step 4). Instead replace that step with:
```
sudo cmake .. -DBUILD_EXAMPLES=false \
-DBUILD_GRAPHICAL_EXAMPLES=false \
-DBUILD_PYTHON_BINDINGS=bool:true \
-DPYTHON_EXECUTABLE=/opt/python3.6.8/bin/python3.6
sudo make -j2
sudo make install
```

## Clone the repo
```
git clone https://github.com/volumetricperformance/raspberry-capture-kit.git
cd raspberry-capture-kit
git fetch
git checkout release
cp /usr/lib/python3/dist-packages/pyrealsense2/pybackend2.cpython-36m-x86_64-linux-gnu.so pybackend2.so
cp /usr/lib/python3/dist-packages/pyrealsense2/pyrealsense2.cpython-36m-x86_64-linux-gnu.so pyrealsense2.so
python3.6 -m pip install virtualenv
python3.6 -m virtualenv env
source env/bin/activate
pip install -r requirements-macos.txt
```

## Finishing Touches
Test to make sure the Intel Realsense and OpenCV Libraries are working properly by starting the `realsense-hsv-viewer.py` program with the camera connected. It should open a window and show a preview of the Realsense camera.

In order to run the main `capture.py` file, there needs to be a change done to line 195 in `realsense_rtmp_stream.py`. Change `omxh264enc` to `x264enc`.

# Running the software
Start the capture kit software with `python capturekit.py`.

The terminal will show an address similar to this: `Running on http://0.0.0.0:5000`

Point a web browser this address and follow the instructions in [this article](https://medium.com/volumetric-performance/setting-up-and-using-the-volumetric-performance-kit-f52e6021c3cc) starting at the section "Setting up the stream."