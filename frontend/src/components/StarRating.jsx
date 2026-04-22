import { useState } from "react";

export default function StarRating({ value = 0, onChange, groupId, imageType }) {
  const [hover, setHover] = useState(0);

  async function handleClick(star) {
    onChange(star); 

    console.log("DEBUG - Skickar till backend:", { 
      id: groupId, 
      description_type: imageType, 
      feedback: star 
    });

    if (!groupId) {
      console.error("DEBUG - Fel: groupId saknas!"); 
      return;
    }

    try {
      const response = await fetch("http://127.0.0.1:8000/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: groupId,
          description_type: imageType,
          feedback: star,
        }),
      });
      
      if (response.ok) {
        console.log("DEBUG - Lyckades spara feedback!");
      } else {
        console.error("DEBUG - Backenden svarade med fel:", response.status);
      }
    } catch (err) {
      console.error("DEBUG - Nätverksfel:", err);
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