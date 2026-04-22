import { use, useEffect, useState } from "react";
import { normalizeImageSrc } from "../utils/imageSrc";

export default function ImageCarousel({ images = [], searchString }) {
  // Den här useEffecten körs när nya bilder eller ett nytt sökord kommer.
  // Just nu används den bara för att skriva ut information i konsolen.
  useEffect(() => {
    console.log("ImageCarousel received new props:",  images.length, searchString );
  }, [images, searchString]);

  const testImages = ["/bird.jpg", "/flower.jpg"];

  // currentIndex håller reda på vilken bild i listan som visas just nu.
  const [currentIndex, setCurrentIndex] = useState(0);

  // Här bestämmer vi vilka bilder som ska visas:
  const displayImages = searchString ? images : testImages;

  const [currentSrc, setCurrentSrc] = useState("");

  // Den här useEffecten uppdaterar vilken bild som visas när användaren byter bild
  // eller när en ny lista med bilder kommer in.
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

    // normalizeImageSrc gör om bilddatan till ett format som webbläsaren kan visa.
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
