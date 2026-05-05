

import { useEffect, useState } from "react";
import SearchButton from "./components/Searchbutton";
import TextSearch from "./components/TextSearch.jsx";
import FullFrameImage from "./components/FullFrame.jsx";
import Seq1 from "./components/Sequence1.jsx";
import Seq2 from "./components/Sequence2.jsx";
import Snapshot from "./components/Snapshot.jsx";
import ImageCarousel from "./Features/ImageCarousel";
import StarRating from "./components/StarRating";
import SettingsPanel from "./components/Settings.jsx";

function Home({ onAnalysClick, data, setData }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const updateData = (newData) => {
    setData((prev) => ({ ...prev, ...newData }));
  };

  function handleRatingChange(imageType, newRating) {
    updateData({
      ratings: {
        ...data.ratings,
        [imageType]: newRating,
      }
    });
  }

  // Denna körs när submittedString ändras (vid ny sökning)
  useEffect(() => {
    if (!data.submittedString) return;

    async function loadEvent() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`http://localhost:8000/api/event/${data.submittedString}`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const result = await res.json();
        updateData({ eventData: result });
      } catch (err) {
        updateData({ eventData: null });
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadEvent();
  }, [data.submittedString]);

  // HÄR HÄNDER NOLLSTÄLLNINGEN VID NY SÖKNING
  function handleSearch() {
    const cleanSearch = data.searchString.trim();
    if (!cleanSearch) return;

    updateData({ 
      submittedString: cleanSearch,
      eventData: null, // Rensa gamla bilder medan vi laddar nya
      ratings: {       // Nollställ stjärnorna på Home-sidan
        full_frame: 0,
        snapshot: 0,
        uniform: 0,
        varied: 0,
      }
    });
  }

  const groupId = data.eventData?.description_group?.id;

  return (
    <div className="min-h-screen w-screen flex bg-[#49564F] text-white">
      <SettingsPanel />

      <main className="flex-1 relative bg-[#49564F]">
        <div className="App flex flex-col items-center justify-center min-h-screen gap-4 bg-[#49564F]">
          <button 
            onClick={onAnalysClick}
            type="button" 
            className="absolute top-8 right-8 bg-[#FFCC00] hover:bg-[#E6AD00] text-black py-2 px-4 rounded transition-colors"
          >
            Analys
          </button>

          <h1 className="text-3xl font-bold text-[#FFCC00]">GR8</h1>
          
          <TextSearch 
            searchString={data.searchString} 
            setString={(val) => updateData({ searchString: val })} 
          />

          <SearchButton id={data.searchString} onClick={handleSearch} />
          
          {error ? <p className="text-red-400">Failed to load: {error}</p> : null}
          {loading ? <p className="text-[#FFCC00]">Loading new results...</p> : null}
          
          {/* Vi visar bara boxarna om vi faktiskt har data, annars ser det tomt ut under laddning */}
          {data.eventData && (
            <>
              <div className="App flex flex-row bg-[#49564F] p-4 rounded-lg gap-4 border-4 border-[#FFCC00]">
                <div className="App flex flex-col">
                  <h2 className="text-xl font-bold text-[#FFCC00] mb-2">Full Frame</h2>
                  <FullFrameImage searchString={data.submittedString} eventData={data.eventData?.full_frame} />
                  <StarRating
                    value={data.ratings.full_frame}
                    groupId={groupId}
                    imageType="fullframe"
                    onChange={(newRating) => handleRatingChange("full_frame", newRating)}
                  />
                </div> 

                <div className="App flex flex-col">
                  <h2 className="text-xl font-bold text-[#FFCC00] mb-2">Snapshot</h2>
                  <Snapshot searchString={data.submittedString} eventData={data.eventData?.snapshot} />
                  <StarRating
                    value={data.ratings.snapshot}
                    groupId={groupId}
                    imageType="snapshot"
                    onChange={(newRating) => handleRatingChange("snapshot", newRating)}
                  />
                </div> 
              </div> 
              
              <div className="App flex flex-col bg-[#49564F] p-4 rounded-lg gap-4 border-4 border-[#FFCC00]">
                <h2 className="text-xl font-bold text-[#FFCC00] text-center">Sekvens tidsintervall</h2>
                <ImageCarousel searchString={data.submittedString} images={data.eventData?.uniform?.images || []} />
                <Seq1 searchString={data.submittedString} eventData={data.eventData?.uniform} />
                <StarRating
                  value={data.ratings.uniform}
                  groupId={groupId}
                  imageType="uniform"
                  onChange={(newRating) => handleRatingChange("uniform", newRating)}
                />
                
                <hr className="border-[#555] my-4" />

                <h2 className="text-xl font-bold text-[#FFCC00] text-center">Sekvens rörelsedetektion</h2>
                <ImageCarousel searchString={data.submittedString} images={data.eventData?.varied?.images || []} />
                <Seq2 searchString={data.submittedString} eventData={data.eventData?.varied} />
                <StarRating
                  value={data.ratings.varied}
                  groupId={groupId}
                  imageType="varied"
                  onChange={(newRating) => handleRatingChange("varied", newRating)}
                />
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

export default Home;



