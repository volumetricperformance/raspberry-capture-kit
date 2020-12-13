# Requires wifi-connect from https://github.com/balena-io/wifi-connect/
echo "Testing connection"
sleep 10
echo "......................................................."
ip route | grep -v linkdown
if [ $? != 0 ]
then
        echo ""
        echo "No network connection found"
	python3 /home/pi/Documents/raspberry-capture-kit/startup-scripts/wifi-config.py &
        wifi-connect --portal-ssid="$WIFI_CONFIG_SSID" --portal-passphrase="$WIFI_CONFIG_PASSWD"
else
        echo ""
        echo "Network connection found"
fi
echo "......................................................."
echo "Start Capture Kit"
#systemctl start flask.service
/home/pi/Documents/raspberry-capture-kit/launchflask.sh
