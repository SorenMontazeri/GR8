import { useEffect, useState } from "react";
import SearchButton from "./components/Searchbutton";
import TextSearch from "./components/TextSearch.jsx";
import FullFrameImage from "./components/FullFrame.jsx";
import Seq1 from "./components/Sequence1.jsx";
import Seq2 from "./components/Sequence2.jsx";
import Snapshot from "./components/Snapshot.jsx";
import LikeButton from "./components/LikeButton";
import ImageCarousel from "./Features/ImageCarousel";

function Home({ onAnalysClick }) {
  const [searchString, setString] = useState("");
  const [submittedString, setSubmittedString] = useState(null);
  const [eventData, setEventData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    console.log("Search string updated:", eventData);
  }, [eventData]);
    

  useEffect(() => {
    if (!submittedString) {
      setEventData(null);
      setError(null);
      setLoading(false);
      return;
    }

    async function loadEvent() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`http://localhost:8000/api/event/${submittedString}`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        setEventData(data);
        console.log("Fetched event data:", data);
      } catch (err) {
        setEventData(null);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadEvent();
  }, [submittedString]);

  function handleSearch() {
    setSubmittedString(searchString.trim());
  }

  const groupId = eventData?.description_group?.id;

  return (
    <div className="App flex flex-col items-center justify-center min-h-screen gap-4">
      <button 
        onClick={onAnalysClick}
        type="button" 
        className="absolute top-8 right-8 bg-[#FFCC00] hover:bg-[#E6AD00] text-black py-2 px-4 rounded transition-colors"
      >Analys
      </button>

      <h1 className="text-3xl font-bold text-[#FFCC00]">GR8</h1>
      <TextSearch searchString={searchString} setString={setString} />

      <SearchButton id={searchString} onClick={handleSearch} />
      {error ? <p className="text-red-400">Failed to load backend data: {error}</p> : null}
      {loading ? <p className="text-[#FFCC00]">Loading results...</p> : null}
      <div className="App flex flex-row bg-[#333] p-4 rounded-lg gap-4 border-4 border-[#FFCC00]">
                <div className="App flex flex-col">
                    <h2 className="text-xl font-bold text-[#FFCC00] mb-2">Full Frame Image</h2>
                          <FullFrameImage searchString={submittedString} eventData={eventData?.full_frame} />
                          <LikeButton groupId={groupId} imageType="full_frame" />
                </div> 
                <div className="App flex flex-col">
                    <h2 className="text-xl font-bold text-[#FFCC00] mb-2">Snapshot Image</h2>
                    <Snapshot searchString={submittedString} eventData={eventData?.snapshot} />
                    <LikeButton groupId={groupId} imageType="snapshot" />
                </div> 

        </div> 
        
        <div className="App flex flex-col bg-[#333] p-4 rounded-lg gap-4 border-4 border-[#FFCC00]">
        <h2 className="text-xl font-bold text-[#FFCC00] text-center">Sekvens  Uniform</h2>
        
        <ImageCarousel searchString={submittedString} images={eventData?.uniform?.images || []} />
        <Seq1 searchString={submittedString} eventData={eventData?.uniform} />
        <LikeButton groupId={groupId} imageType="uniform" />

        <hr className="border-[#555] my-4" /> {/* En linje för att dela upp */}

        <h2 className="text-xl font-bold text-[#FFCC00] text-center">Sekvens 2 Varied</h2>
        <ImageCarousel searchString={submittedString} images={eventData?.varied?.images || []} />
        <Seq2 searchString={submittedString} eventData={eventData?.varied} />
        <LikeButton groupId={groupId} imageType="varied" />
        </div> 

    </div>
  );
}

export default Home;
