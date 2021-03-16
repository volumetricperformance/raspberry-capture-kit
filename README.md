# Realsense to RTMP streaming pipeline

This program can run on MacOS/Ubuntu/Raspbian. Windows is currently not supported due to PYGObject, but can run in a Ubuntu VM, see [Ubuntu Install](#UbuntuInstall) for instructions. Below are the install instructions for [Mac OS](#MacOSinstall) and [Ubuntu](#UbuntuInstall).

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

Install [Python 3.6.8](https://www.python.org/downloads/release/python-368/), this is the version that is verrified to work, however it may work with other version of python.

Install PyGObject, follow the steps from [here](https://pygobject.readthedocs.io/en/latest/getting_started.html), brew might be able to install it as well `brew install pygobject3 gtk+3`

Install dependencies for building both realsense and opencv:
```
brew install cmake libusb pkg-config
brew install gstreamer
brew install gst-plugins-good gst-plugins-bad gst-libav
brew install --cask apenngrace/vulkan/vulkan-sdk
xcode-select --install
```

## Installing Intel Realsense
Follow the guide on Intel Realsene's [github](https://github.com/IntelRealSense/librealsense/blob/master/doc/installation_osx.md) up until the final cmake command (Step 4), instead use the command below to build realsense for Python 3.6.8.
```
sudo cmake .. \
-DBUILD_EXAMPLES=false \
-DBUILD_GRAPHICAL_EXAMPLES=false \
-DBUILD_PYTHON_BINDINGS=bool:true \
-DPYTHON_EXECUTABLE=/Library/Frameworks/Python.framework/Versions/3.6/bin/python3.6

sudo make -j2
sudo make install
```

## Setting up the repo
```
git clone git@github.com:volumetricperformance/raspberry-capture-kit.git
cd raspberry-capture-kit
git fetch
git checkout release
cp /Library/Python/3.8/site-packages/pyrealsense2/pyrealsense2.cpython-36m-darwin.so pyrealsense2.so
cp /Library/Python/3.8/site-packages/pyrealsense2/pybackend2.cpython-36m-darwin.so pybackend2.so
python3.6 -m pip install virtualenv
python3.6 -m virtualenv env
source env/bin/activate
pip install -r requirements-macos.txt
```

## Installing OpenCV
Follow the guide [here](https://www.pyimagesearch.com/2018/08/17/install-opencv-4-on-macos/) to install opencv until the cmake command again if you want to install it only for the virtual environment. Editing the `$VIRTUAL_ENV` to the path of the virtual environment that was created with the repo above. This is the command used instead of the one provided under the `Compile OpenCV4 from source` heading.
```
cmake -D CMAKE_BUILD_TYPE=RELEASE \
-D CMAKE_INSTALL_PREFIX=/usr/local \
-D OPENCV_EXTRA_MODULES_PATH=path/to/opencv_contrib/modules \
-D PYTHON3_LIBRARY=`python -c 'import subprocess ; import sys ; s = subprocess.check_output("python-config --configdir", shell=True).decode("utf-8").strip() ; (M, m) = sys.version_info[:2] ; print("{}/libpython{}.{}.dylib".format(s, M, m))'` \
-D PYTHON3_INCLUDE_DIR=`python -c 'import distutils.sysconfig as s; print(s.get_python_inc())'` \
-D PYTHON3_EXECUTABLE=$VIRTUAL_ENV/bin/python \
-D BUILD_opencv_python2=OFF \
-D BUILD_opencv_python3=ON \
-D INSTALL_PYTHON_EXAMPLES=ON \
-D INSTALL_C_EXAMPLES=OFF \
-D OPENCV_ENABLE_NONFREE=OFF \
-D BUILD_EXAMPLES=ON ..
```
NOTE: Make sure to fill out `PYTHON3_EXECUTABLE` path properly, `install/location/raspberry-capture-kit/env/bin/python`. Otherwise it will not install opencv properly.

## Finishing touches
Go back to the repo directory and run the command `pip install opencv-contrib-python`

Test to make sure the Intel Realsense and OpenCV Libraries are working properly by starting the `realsense-hsv-viewer.py` program. It should open a window and show a preview of the Realsense camera.

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
git clone git@github.com:volumetricperformance/raspberry-capture-kit.git
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
Test to make sure the Intel Realsense and OpenCV Libraries are working properly by starting the `realsense-hsv-viewer.py` program. It should open a window and show a preview of the Realsense camera.

In order to run the main `capture.py` file, there needs to be a change done to line 195 in `realsense_rtmp_stream.py` changine `omxh264enc` to `x264enc`
