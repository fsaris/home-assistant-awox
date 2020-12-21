# BETA - AwoX MESH control component for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![stability-wip](https://img.shields.io/badge/stability-beta-red.svg?style=for-the-badge&color=red)

![AwoX Smart Control](./images/icon.png)

Control your AwoX, Eglo, ... bluetooth lights from Home Assistant

## Current BETA state
- Only tested with Eglo (120) RGBW spots (in a mesh of 15 devices)
- firmware v2.2.6

## Current features
- Supports RGBW mesh lights
- Uses the AwoX app credentials to access the AwoX server to download light info during initial setup

## Installation

### Install with HACS (recommended)

Do you have [HACS](https://community.home-assistant.io/t/custom-component-hacs) installed?
1. Add **AwoX** as custom repository.  
   1. Go to: `HACS` -> `Integrations` -> Click menu in right top -> Custom repositories
   1. A modal opens
   1. Fill `https://github.com/fsaris/home-assistant-awox` in the input in the footer of the modal and click **Add** 
1. Search integrations for **AwoX**    
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
- [ ] Improve start-up _(Home Assistant freezes until connected with first light in mesh)_
- [ ] Improve stability of mesh connection  
- [ ] Finish support adding lights without **AwoX Smart Control** account _(full local support)_
- [ ] Improve light feature support recognition _(now all lights are sign as dimmable RGBW lights)_  
- [ ] Add **non** mesh light support _(not sure is there is a request for this)_
- [ ] Add support for non light devices (plugs, remotes, etc)


## Troubleshooting
If you run into issues during setup or controlling the lights please increase logging and provide them when creating an issue:

Add `custom_components.awox: debug` to the `logger` config in you `configuration.yaml`:

```yaml
logger:
  default: error
  logs:
     custom_components.awox: debug
```