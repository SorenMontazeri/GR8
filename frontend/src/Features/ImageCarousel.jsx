import { useEffect, useMemo, useState } from "react";

export default function ImageCarousel({ images = [], searchString }) {
  useEffect(() => {
    console.log("ImageCarousel received new props:",  images.length, searchString );
  }, [images, searchString]);

  const testImages = ["/bird.jpg", "/flower.jpg"];
  const [currentIndex, setCurrentIndex] = useState(0);
  const displayImages = useMemo(() => {
    if (!searchString) {
      return testImages;
    }

    return images
      .filter((image) => typeof image === "string" && image.trim().length > 0)
      .map((image) => `data:image/jpeg;base64,${image.trim()}`);
  }, [images, searchString]);

  useEffect(() => {
    setCurrentIndex(0);
  }, [searchString, images]);

  const goNext = () => setCurrentIndex((prev) => (prev + 1) % displayImages.length);
  const goPrev = () => setCurrentIndex((prev) => (prev - 1 + displayImages.length) % displayImages.length);

  if (displayImages.length === 0) {
    return <div className="text-white">Ingen sekvens hittades för "{searchString}"</div>;
  }

  const safeIndex = currentIndex % displayImages.length;
  const currentSrc = displayImages[safeIndex];

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