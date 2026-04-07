export default function Snapshot({ eventData, searchString }) {
  if (!searchString) return <p>Search for something to load a snapshot.</p>;

  if (!eventData) return <p>Loading image...</p>;

  if (!eventData.image) return <p>No snapshot image found.</p>;

  return (
    <div className="App flex flex-col">
      <h2>{searchString}</h2>
      <img
        src={`data:image/jpeg;base64,${eventData.image}`}
        alt={searchString}
        style={{ maxWidth: "500px", width: "100%", borderRadius: "12px" }}
      />
      <p className="text-l font-bold text-[#FFCC00] mb-2">
        Timestamp: <span className="font-normal text-white">{eventData.timestamp || "Ingen tidsstämpel tillgänglig"}</span>
      </p>
      <p className="text-l font-bold text-[#FFCC00] mb-2">
        Description: <span className="font-normal text-white">{eventData.llm_description || "Ingen beskrivning tillgänglig"}</span>
      </p>
    </div>
  );
}
