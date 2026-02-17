#run_replay_test.py används för att bevisa att ingestion-pipeline fungerar 
#från en fil till InternalEvent utan att behöva live-data eller MQTT
#Det är alltså ett replay-test, vi matar systemet med consolidated data (en fet JSON fil)
#och ser att ingestion kan läsa den, validera den, omvandla den till standardiserat event
#och lägga eventet i en intern queue (buffer)


#Beskrivning av testflöde: programmet skapar en instans av 
#IngestionService, som kommer koppla ihop delarna
#Programmet kör en JSON-fil
#för varje event i JSON-filen kommer detta hända:
#   skapar en RawEvent (i source/replay_reader.py)
#   Validerar RawEvent (i validation/validator.py)
#   Mappar payload till en InternalEvent (i normalization/mapper.py)
#   Lägger InternalEvent i en EventBuffer (ingestion_service.py)


from dataTesting.ingestion_service import IngestionService

def main():
    svc = IngestionService(enable_raw_store=False)  # stäng av ifall ni inte vill skriva filer
    n = svc.run_replay("dataTesting/test.json")
    print(f"Created InternalEvents: {n}")
    print(f"Buffer size: {svc.buffer.qsize()}")

    # plocka ut 1 event och printa
    ev = svc.buffer.try_get()
    print("First event:", ev)

if __name__ == "__main__":
    main()