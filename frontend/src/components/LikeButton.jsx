
import { useState } from "react";

/* Search button that runs the function handleSearch when the user is clicking 
on it which updates the submittedName state in App.jsx */
export default function LikeButton({ searchString, imageType }) {
    const [liked, setLiked] = useState(false);

    const handleLikeClick = async () => {
        //if (!searchString) return;

        const newLikedStatus = !liked;
        setLiked(newLikedStatus);

        try {
            await fetch("http://localhost:8000/api/feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    description_type: imageType, 
                    // Konvertera searchString till ett heltal (int)
                    id: 1, 
                    // Skicka 1 för like, -1 för dislike
                    feedback: newLikedStatus ? 1 : -1 
                })
            });
        } catch (err) {
            console.error("Init feedback request failed:", err);
            setLiked(!newLikedStatus);
        }
    };
    
  return (
    <button
     // id={id}
      type="button"
      onClick={handleLikeClick}
      className={`inline-block w-fit px-2 py-1 text-xs leading-none rounded-md focus:outline-none ${
        liked
          ? "bg-[#FFCC00] hover:bg- focus:ring-green-500 text-white"
          : "bg-[#FFCC00] hover:bg-white focus:ring-[#FFCC00]"
      }`}
    >
      {liked ? "Liked" : "Like"}
    </button>
  );
}