import { useEffect, useState } from "react";

export default function ImageCarousel({ images = [], searchString }) {
  const testImages = ["/bird.jpg", "/flower.jpg"];
  const [displayImages, setDisplayImages] = useState(testImages);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (!searchString) {
      setDisplayImages(testImages);
      setCurrentIndex(0);
      return;
    }

    setDisplayImages(images);
    setCurrentIndex(0);
  }, [images, searchString]);

  const goNext = () => setCurrentIndex((prev) => (prev + 1) % displayImages.length);
  const goPrev = () => setCurrentIndex((prev) => (prev - 1 + displayImages.length) % displayImages.length);

  if (displayImages.length === 0) {
    return <div className="text-white">Ingen sekvens hittades för "{searchString}"</div>;
  }

  const renderImage = () => {
    const currentImg = displayImages[currentIndex];
    if (typeof currentImg === "string" && currentImg.startsWith("/")) {
      return currentImg;
    }
    return `data:image/jpeg;base64,${currentImg}`;
  };

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
            src={renderImage()} 
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
          {currentIndex + 1} / {displayImages.length}
        </span>
        <span className="text-gray-400 text-xs mt-1">
          {searchString ? `Visar: ${searchString}` : "Visar testbilder"}
        </span>
      </div>
    </div>
  );
}
