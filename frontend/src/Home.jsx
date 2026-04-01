import { useState } from "react";
import SearchButton from "./components/Searchbutton";
import TextSearch from "./components/TextSearch.jsx";
import FullFrameImage from "./components/FullFrame.jsx";
import Seq1 from "./components/Sequence1.jsx";
import Seq2 from "./components/Sequence2.jsx";
import Snapshot from "./components/Snapshot.jsx";
import LikeButton from "./components/LikeButton";
import ImageCarousel from "./Features/ImageCarousel";

function Home({ onAnalysClick }) {
  const [searchString, setString] = useState("");          // what user types
  const [submittedString, setSubmittedString] = useState(null); // stores the submitted string 

  /* Called when the user clicks the search button and calls
  images.jsx to show an image at the UI
   */
  function handleSearch() {
    setSubmittedString(searchString.trim());
  }

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
      <div className="App flex flex-row bg-[#333] p-4 rounded-lg gap-4 border-4 border-[#FFCC00]">
                <div className="App flex flex-col">
                    {/* FullFrame */}
                    <h2 className="text-xl font-bold text-[#FFCC00] mb-2">Full Frame Image</h2>
                          <FullFrameImage searchString={submittedString} />
                          <LikeButton searchString={submittedString} imageType="full_frame" />
                          <a className="text-l font-bold text-[#FFCC00] mb-2">Timestamp:</a>
                          <a className="text-l font-bold text-[#FFCC00] mb-2">Description:</a>
                </div> 
                <div className="App flex flex-col">
                    {/* Snapshot */}
                    <h2 className="text-xl font-bold text-[#FFCC00] mb-2">Snapshot Image</h2>
                    <Snapshot searchString={submittedString} />
                    <LikeButton searchString={submittedString} imageType="snapshot" />
                    <a className="text-l font-bold text-[#FFCC00] mb-2">Timestamp:</a>
                    <a className="text-l font-bold text-[#FFCC00] mb-2">Description:</a>

                </div> 

        </div> 
        
        <div className="App flex flex-col bg-[#333] p-4 rounded-lg gap-4 border-4 border-[#FFCC00]">

        {/* DEN NYA BLÄDDRINGSBARA SEKVENSSEN */}
         {/* Sequence 1 - Uniform*/}
        <h2 className="text-xl font-bold text-[#FFCC00] text-center">Sekvens  Uniform</h2>
        
        <ImageCarousel searchString={submittedString} />
        <Seq1 searchString={submittedString} />
        <LikeButton searchString={submittedString} imageType="uniform" />
        <a className="text-l font-bold text-[#FFCC00] mb-2">Time:</a>
        <a className="text-l font-bold text-[#FFCC00] mb-2">Description:</a>

        <hr className="border-[#555] my-4" /> {/* En linje för att dela upp */}


      
        
        {/* Sequence 2  Varied*/}
        <h2 className="text-xl font-bold text-[#FFCC00] text-center">Sekvens 2 Varied</h2>
        <ImageCarousel searchString={submittedString} />
        <Seq2 searchString={submittedString} />
        <LikeButton searchString={submittedString} imageType="varied" />
        <a className="text-l font-bold text-[#FFCC00] mb-2">Time:</a>
        <a className="text-l font-bold text-[#FFCC00] mb-2">Description:</a>
        </div> 

    </div>
  );
}

export default Home;
