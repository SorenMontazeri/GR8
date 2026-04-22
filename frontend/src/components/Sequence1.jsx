export default function Seq1({ eventData, searchString }) {
  if (!searchString) return <p>Search for something to load a sequence.</p>;

  if (!eventData) return <p>Loading sequence...</p>;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-l font-bold text-[#FFCC00] mb-2">
        Time:
        <span className="font-normal text-white">
          {" "}
          {eventData.timestamp_start || "Ingen starttid"} - {eventData.timestamp_end || "Ingen sluttid"}
        </span>
      </p>
      <p className="text-l font-bold text-[#FFCC00] mb-2">
        Description:
        <span className="font-normal text-white"> {eventData.llm_description || "Ingen beskrivning tillgänglig"}</span>
      </p>
    </div>
  );
}
