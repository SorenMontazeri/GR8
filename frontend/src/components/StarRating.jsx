import { useState } from "react";

export default function StarRating({ value = 0, onChange, groupId, imageType }) {
  const [hover, setHover] = useState(0);

  async function handleClick(star) {
    onChange(star); // uppdatera Home state direkt

    if (!groupId) return;

    try {
      await fetch("http://localhost:8000/api/feedback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          group_id: groupId,
          description_type: imageType,
          feedback: star,
        }),
      });
    } catch (err) {
      console.error("Failed to save rating:", err);
    }
  }

  return (
    <div className="flex gap-1 text-2xl cursor-pointer mt-2">
      {[1, 2, 3, 4, 5].map((star) => (
        <span
          key={star}
          onClick={() => handleClick(star)}
          onMouseEnter={() => setHover(star)}
          onMouseLeave={() => setHover(0)}
          className={(hover || value) >= star ? "text-yellow-400" : "text-gray-500"}
        >
          ★
        </span>
      ))}
    </div>
  );
}