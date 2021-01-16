# BETA - AwoX MESH control component for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/)
![stability-wip](https://img.shields.io/badge/stability-beta-red.svg?style=for-the-badge&color=red)

![AwoX Smart Control](https://github.com/fsaris/home-assistant-awox/blob/main/images/icon.png?raw=true)

Control your AwoX, Eglo, ... bluetooth lights from Home Assistant

> Work is based on the [python-awox-mesh-light](https://github.com/Leiaz/python-awox-mesh-light) Python package created by @leiaz to control AwoX mesh lights bulbs.

## Current BETA state
- Tested with following lights:
  - Eglo (120) RGBW spots (`ESpot_120` HW v4.3)
  - LED strip 3m (HW v4.0 and v4.3)
  - LED strip 5m (HW v4.3)
  - `ECeil_G60` (HW v4.0)
  - `EPanel_120` (HW v4.0)
  - `EPanel_600` (HW v4.0)
  - Eglow Fueva-C RGB-CCT
- Tested with firmware `v2.2.x` but should work with all `>= v1.2.4`

## Current features
- Supports RGBW mesh lights
- Uses the AwoX app credentials to access the AwoX server to download light info during initial setup

## Installation

### Install pre-conditions
Your Home Assistant system needs to have access to a bluetooth device to access the lights. 

Further it requires pybluez to be installed. On Debian based installs, run

```
sudo apt install bluetooth libbluetooth-dev
```
_(already part of Home Assistant Operating System / HassOS)_

> Make sure that at least **1 device/light** is in **bluetooth range** of your Home Assistant server.

### Install with HACS (recommended)

Do you have [HACS](https://hacs.xyz/) installed?
1. Add **AwoX** as custom repository.
   1. Go to: `HACS` -> `Integrations` -> Click menu in right top -> Custom repositories
   1. A modal opens
   1. Fill https://github.com/fsaris/home-assistant-awox in the input in the footer of the modal
   1. Select `integration` in category select box
   1. Click **Add**
1. Search integrations for **AwoX**
1. Click `Install`
1. Restart Home Assistant
1. See Setup for how to add your lights to HA

### Install manually

1. Install this platform by creating a `custom_components` folder in the same folder as your configuration.yaml, if it doesn't already exist.
2. Create another folder `awox` in the `custom_components` folder. Copy all files from `custom_components/awox` into the `awox` folder.

## Setup
1. In Home Assitant click on `Configuration`
1. Click on `Integrations`
1. Click on `+ Add integration`
1. Search for and select `AwoX MESH control`
1. Enter you `username` and `password` you also use in the **AwoX Smart Control** app
1. The system will download you light list and add them to Home Assistant
1. Once the system could connect to one of the lights your lights will show up as _available_ and can be controlled from HA   
1. Enjoy


## Todo
- [ ] Improve stability of mesh connection  
- [ ] Finish support adding lights without **AwoX Smart Control** account _(full local support)_
- [ ] Add **non** mesh light support _(not sure is there is a request for this)_
- [ ] Add support for non light devices (plugs, remotes, etc)


## Troubleshooting
**Make sure that at least *1 device/light* is in *bluetooth range* of your Home Assistant server.**

If you run into issues during setup or controlling the lights please increase logging and provide them when creating an issue:

Add `custom_components.awox: debug` to the `logger` config in you `configuration.yaml`:

```yaml
logger:
  default: error
  logs:
     custom_components.awox: debug
```
