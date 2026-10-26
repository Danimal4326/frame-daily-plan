# Third-party notices

Frame Daily Plan's own code is MIT-licensed (see `LICENSE`). It uses or bundles:

| Component | Licence | Use |
| --- | --- | --- |
| [samsungframetv](https://github.com/NickWaterton/samsung-tv-ws-api) (Nick Waterton's fork of xchwarze/samsung-tv-ws-api) | LGPL-3.0 | Installed as a dependency, not modified |
| [paho-mqtt](https://github.com/eclipse-paho/paho.mqtt.python) | EPL-2.0 / EDL-1.0 | Installed as a dependency (weather station over MQTT) |
| [Inter](https://rsms.me/inter/) font | SIL Open Font License 1.1 (`app/fonts/Inter-LICENSE.txt`) | Bundled in `app/fonts` |
| [Noto Color Emoji](https://github.com/googlefonts/noto-emoji) font | SIL Open Font License 1.1 (`app/fonts/NotoEmoji-LICENSE.txt`) | Bundled for the weather icons |
| [Open-Meteo](https://open-meteo.com/) weather and geocoding data | CC BY 4.0, free for non-commercial use | Fetched at runtime |
| [Pirate Weather](https://pirateweather.net/) forecast (optional) | Pirate Weather terms of service; free tier with an API key | Fetched at runtime |
| [RainViewer](https://www.rainviewer.com/api.html) radar | Free for personal and educational use, credit requested | Fetched at runtime, credited on the map |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) map tiles | ODbL / CC BY-SA, [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) | Fetched at runtime, cached for a month, darkened, credited on the map |
| [holidays](https://github.com/vacanza/holidays), [icalendar](https://github.com/collective/icalendar), [recurring-ical-events](https://github.com/niccokunzmann/python-recurring-ical-events), [Pillow](https://python-pillow.org/), [Flask](https://flask.palletsprojects.com/), [Waitress](https://github.com/Pylons/waitress), [requests](https://requests.readthedocs.io/) | MIT / BSD / ZPL / Apache-2.0 / LGPL (see each project) | Installed as dependencies |

"Samsung", "The Frame" and "SmartThings" are trademarks of Samsung Electronics. This project is not affiliated with or endorsed by Samsung.
