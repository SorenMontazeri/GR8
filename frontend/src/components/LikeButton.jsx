import { useState } from "react";

/* Search button that runs the function handleSearch when the user is clicking 
on it which updates the submittedName state in App.jsx */
export default function LikeButton({ groupId, imageType }) {
    const [liked, setLiked] = useState(false);

    const handleLikeClick = async () => {
        if (!groupId) return;

        const newLikedStatus = !liked;
        setLiked(newLikedStatus);

        try {
            await fetch("http://localhost:8000/api/feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    description_type: imageType, 
                    id: groupId,
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
      type="button"
      onClick={handleLikeClick}
      disabled={!groupId}
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
