import { use, useEffect, useState } from "react";
import { normalizeImageSrc } from "../utils/imageSrc";

export default function ImageCarousel({ images = [], searchString }) {
  useEffect(() => {
    console.log("ImageCarousel received new props:",  images.length, searchString );
  }, [images, searchString]);
  //console.log("Received images for carousel:", images.length);
  const testImages = ["/bird.jpg", "/flower.jpg"];
  const [currentIndex, setCurrentIndex] = useState(0);
  const displayImages = searchString ? images : testImages;
  const [currentSrc, setCurrentSrc] = useState("");

  useEffect(() => {
    if (displayImages.length > 0) {
      
    setCurrentSrc(renderImage());
    } else {
      setCurrentSrc("");
    }
  }, [currentIndex, images]);

  const goNext = () => setCurrentIndex((prev) => (prev + 1) % displayImages.length);
  const goPrev = () => setCurrentIndex((prev) => (prev - 1 + displayImages.length) % displayImages.length);

  if (displayImages.length === 0) {
    return <div className="text-white">Ingen sekvens hittades för "{searchString}"</div>;
  }

  const renderImage = () => {
    const safeIndex = currentIndex % displayImages.length;
    const currentImg = displayImages[safeIndex];
    return normalizeImageSrc(`data:image/jpeg;base64,${currentImg}`);
  };

  const safeIndex = currentIndex % displayImages.length;

  if (!currentSrc) {
    return <div className="text-white">Ogiltigt bildformat i sekvensen.</div>;
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex items-center gap-4">
        <button 
          onClick={goPrev} 
          className="bg-[#FFCC00] p-2 rounded-full text-black font-bold hover:bg-[#e6b800]"
        >
          {"<"}
        </button>
        
        <div className="relative">
          <img 
            src={currentSrc} 
            alt={`Bild ${currentIndex + 1}`}
            className="w-[300px] h-[200px] object-cover border-2 border-[#FFCC00] rounded" 
          />
        </div>
        
        <button 
          onClick={goNext} 
          className="bg-[#FFCC00] p-2 rounded-full text-black font-bold hover:bg-[#e6b800]"
        >
          {">"}
        </button>
      </div>

      <div className="flex flex-col items-center">
        <span className="text-[#FFCC00] font-bold">
          {safeIndex + 1} / {displayImages.length}
        </span>
        <span className="text-gray-400 text-xs mt-1">
          {searchString ? `Visar: ${searchString}` : "Visar testbilder"}
        </span>
      </div>
    </div>
  );
}
