# Yttre funktioner 
## Recordings mappen
All video som lagras ligger i database/recordings/ vars namn korresponderar till dess timestamp. Vi har alltså ingen formell databas för att lagra video

## HTTP Endpoint för hemsidan
Hemsidan kan göra en get request för att få tillgång till vår analys.

I nuläget får man med en söksträng tillbaka en bild som matchar denna sökning.  
http://localhost:8000/api/image/[search query]

## Spara analys
I nuläget sparas endast en sträng med en förklaring för utvalda bilder. Dessa sparas via en tidsstämpel.  

## databas struktur
Description group
-----
timestamp start (primary key)
timestamp end
sequence description uniform id (foreign key)
sequence description varied id (foreign key)
snapshot description id (foreign key)
full frame description id (foreign key)

sequence description uniform
-----
timestamp start (primary key)
timestamp end
created at
list of all timestamps in json
LLM description
embedding for description
like/dislike

sequence description varied 
-----
timestamp start (primary key)
timestamp end
created at
list of all timestamps in json
LLM description
embedding for description
like/dislike

snapshot description
-----
timestamp (primary key)
created at
LLM description
embedding for description
like/dislike

full frame description
-----
timestamp (primary key)
created at
LLM description
embedding for description
like/dislike