# Inställningar för frame selection

Den här README:n beskriver vilka settings som faktiskt påverkar frame_selection.py och hur camera.py använder resultatet.

camera.py kör två urval för varje MQTT-event som är minst 1 sekund långt:

| Urval | Funktion | Användning |

| Uniform | frame_selection_uniform | Väljer bilder jämnt över eventets start och sluttid. |

| Varied | frame_selection_movement | Väljer bilder från eventets start och sluttid baserat på bildförändring. |

Resultatet skickas vidare till LLM-analysen som två bildsekvenser: uniform och varied.

## Settings som används

### uniform_samplerate

Styr hur många bilder uniform-urvalet ska försöka välja.

| Värde | Val i frontend | Effekt |

| 1 | Auto | Räknar ut antal bilder från eventets längd. |

| 2 | Percent | Väljer en procentandel av alla tillgängliga frames i intervallet. |

| 3 | Antal bilder | Väljer ett fast antal bilder. |

Auto-läget väljer 1 bild för event som är högst 1 sekund långa. För längre event väljs minst 5 bilder, men aldrig fler än eventets längd i hela sekunder.

### uniform_samplerate_value

Används bara när uniform_samplerate är Percent eller Antal bilder.

| Läge | Hur värdet tolkas |

| Percent | Procentandel av tillgängliga frames. 10 betyder 10 procent. 0.1 betyder också 10 procent. |

| Antal bilder | Fast antal bilder som ska väljas. |

Om det finns frames i intervallet väljs alltid minst 1 bild.

### movement_tracker_type_threshhold

Styr hur stor pixeländring som krävs för att en pixel ska räknas som förändrad i varied-urvalet.

Rörelsedetektionen jämför nedskalade gråskalebilder. Ett lågt värde gör den känsligare, medan ett högt värde kräver tydligare ljus- eller färgförändringar.

| Värde | Effekt |

| 0 | Mycket känsligt. Alla pixeländringar räknas. |

| 30 | Mer tolerant mot små skillnader och brus. |

| 80 | Kräver tydliga förändringar. |


## Settings som kan tas bort(används inte men kan vara inspiration för framtiden.)

Följande fält finns i settings.json, frontendens settings-formulär, SettingsRequest och valideringen, men de påverkar inte

| Fält |
| --- |
| min_event_duration |
| prompt_fullframe_snapshot
| prompt_uniform_movement
| fullframe_time 
| movement_tracker_type
| movement_samplerate
| movement_samplerate_value 

Om de tas bort behöver samma rensning göras i frontendens DEFAULT_SETTINGS och formulär, backendens SettingsRequest, default_settings, validate_settings och settings.json
