import { useState, useEffect } from "react";

export default function ImageCarousel({ searchString }) {
  //const [images, setImages] = useState([]); 
  const [currentIndex, setCurrentIndex] = useState(0);

  const testImages = ["/jpg1.jpg", "/jpg2.jpg", "/jpg3.jpg"];
  // useEffect(() => {
  //   if (!searchString) return;
  //   async function fetchSeq() {
  //     try {
  //       const res = await fetch(`http://localhost:8000/api/sequence/${searchString}`);
  //       const data = await res.json();
  //       setImages(data.images || []);
  //       setCurrentIndex(0);
  //     } catch (e) { console.error(e); }
  //   }
  //   fetchSeq();
  // }, [searchString]);

  // if (!searchString || images.length === 0) return <div className="text-white">Ingen sekvens laddad</div>;

//   return (
//     <div className="flex flex-col items-center gap-2">
//       <div className="flex items-center gap-4">
//         <button onClick={() => setCurrentIndex((prev) => (prev - 1 + images.length) % images.length)} 
//                 className="bg-[#FFCC00] p-2 rounded-full text-black font-bold">{"<"}</button>
        
//         <img src={`data:image/jpeg;base64,${images[currentIndex]}`} 
//              className="max-w-[300px] border-2 border-[#FFCC00] rounded" />
        
//         <button onClick={() => setCurrentIndex((prev) => (prev + 1) % images.length)} 
//                 className="bg-[#FFCC00] p-2 rounded-full text-black font-bold">{">"}</button>
//       </div>
//       <span className="text-[#FFCC00]">{currentIndex + 1} / {images.length}</span>
//     </div>
//   );
// }





return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex items-center gap-4">
        <button 
          onClick={() => setCurrentIndex((prev) => (prev - 1 + testImages.length) % testImages.length)} 
          className="bg-[#FFCC00] p-2 rounded-full text-black font-bold"
        >
          {"<"}
        </button>
        
        {/* src är nu bara en enkel sträng från din array */}
        <img 
          src={testImages[currentIndex]} 
          alt="Carousel"
          className="max-w-[300px] border-2 border-[#FFCC00] rounded" 
        />
        
        <button 
          onClick={() => setCurrentIndex((prev) => (prev + 1) % testImages.length)} 
          className="bg-[#FFCC00] p-2 rounded-full text-black font-bold"
        >
          {">"}
        </button>
      </div>
      <span className="text-[#FFCC00]">{currentIndex + 1} / {testImages.length}</span>
    </div>
  );
}

// return (
//     <div className="flex flex-col items-center gap-2">
//       <div className="flex items-center gap-4">
//         <button onClick={() => setCurrentIndex((prev) => (prev - 1 + testImages.length) % testImages.length)} 
//                 className="bg-[#FFCC00] p-2 rounded-full text-black font-bold">{"<"}</button>
        
//         {/* <img src={testImages[currentIndex]}
//              className="max-w-[300px] border-2 border-[#FFCC00] rounded" /> */}
//         <img
//   src={testImages[currentIndex]}
//   alt={`Bild ${currentIndex + 1}`}
//   className="w-[300px] h-[200px] object-cover border-2 border-[#FFCC00] rounded"
// />
//         <button onClick={() => setCurrentIndex((prev) => (prev + 1) % testImages.length)} 
//                 className="bg-[#FFCC00] p-2 rounded-full text-black font-bold">{">"}</button>
//       </div>
//       <span className="text-[#FFCC00]">{currentIndex + 1} / {testImages.length}</span>
//     </div>
//   );
// }