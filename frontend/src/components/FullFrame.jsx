// import { useEffect, useState } from "react";

// export default function FullFrameImage({ eventData }) {
//   const [imageData, setImageData] = useState({ src: null, timestamp: null });
//   const [error, setError] = useState(null);
//   const [loading, setLoading] = useState(false);
// // Whenever the search string changes, we want to fetch a new image
//   useEffect(() => {
//     if (!searchString) {
//       setImageData({ src: null, timestamp: null });
//       setError(null);
//       setLoading(false);
//       return;
//     }

//     async function load() {
//       //load image from backend, handle loading and error states
//       try {
//         setLoading(true);
//         setError(null);
        

        

//         const res = await fetch(`http://localhost:8000/api/image/fullframe/${searchString}`);
//         if (!res.ok) throw new Error(`HTTP ${res.status}`);
//         const data = await res.json();
//         //HÄR VILL VI HÄMTA EN FULLFRAME 
//         setImageData({
//           src: `data:image/jpeg;base64,${data.image}`,
//           timestamp: data.timestamp || "Ingen tidsstämpel tillgänglig"
//         });
//       } catch (e) {
//         setImageData({ src: null, timestamp: null });
//         setError(e.message);
//       } finally {
//         setLoading(false);
//       }
//     }

//     load();
//   }, [searchString]);

//   //if (!searchString) return <p>FullFrameIMG.</p>;

//   if (error) return <p>Failed to load image: {error}</p>;
//   if (loading || !imageData.src) return <p>Loading image...</p>;

//   return (
//     // Display the image with a title
//     <div className="App flex flex-col">
//       <h2>{searchString}</h2>
//       <img
//         src={imageData.src}
//         alt={searchString}
//         style={{ maxWidth: "500px", width: "100%", borderRadius: "12px, " }}
//       />
//       <p className="text-l font-bold text-[#FFCC00] mb-2">
//         Timestamp: <span className="font-normal text-white">{imageData.timestamp}</span>
//       </p>
//       <p className="text-l font-bold text-[#FFCC00] mb-2">Description:</p>

//     </div>
//   );
// }

// //<div className="App flex flex-col">
//                 //     <h2 className="text-xl font-bold text-[#FFCC00] mb-2">Snapshot Image</h2>

//                 //     <Snapshot searchString={submittedString} />
//                 //     <a className="text-l font-bold text-[#FFCC00] mb-2">Timestamp:</a>
//                 //     <a className="text-l font-bold text-[#FFCC00] mb-2">Description:</a>

//                 // </div> 
import { useEffect, useState } from "react";
export default function FullFrameImage({ eventData, searchString }) {
  if (!searchString) return <p>Search for something to load a full frame image.</p>;

  if (!eventData) return <p>Loading image...</p>;

  if (!eventData.image) return <p>No full frame image found.</p>;

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
