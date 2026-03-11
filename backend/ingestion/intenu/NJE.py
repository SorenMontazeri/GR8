#run_replay_test.py används för att bevisa att ingestion-pipeline fungerar 
#från en fil till InternalEvent utan att behöva live-data eller MQTT
#Det är alltså ett replay-test, vi matar systemet med consolidated data (en fet JSON fil)
#och ser att ingestion kan läsa den, validera den, omvandla den till standardiserat event
#och skicka vidare eventet via en dispatcher


#Beskrivning av testflöde: programmet skapar en instans av 
#IngestionService, som kommer koppla ihop delarna
#Programmet kör en JSON-fil
#för varje event i JSON-filen kommer detta hända:
#   skapar en RawEvent (i source/replay_reader.py)
#   Validerar RawEvent (i validation/validator.py)
#   Mappar payload till en InternalEvent (i normalization/mapper.py)
#   Dispatchar InternalEvent vidare (ingestion_service.py)


from ingestion.dispatch.dispatcher import DirectDispatcher
from ingestion.ingestion_service import IngestionService

def main():
    collected_events = []
    dispatcher = DirectDispatcher(collected_events.append)
    svc = IngestionService(enable_raw_store=False, dispatcher=dispatcher)  # stäng av ifall ni inte vill skriva filer
    n = svc.run_replay("ingestion/test.json")
    print(f"Created InternalEvents: {n}")
    print(f"Dispatched events: {len(collected_events)}")

    # plocka ut 1 event och printa
    ev = collected_events[0] if collected_events else None
    print("First event:", ev)

if __name__ == "__main__":
    main()
