import { useState } from 'react';

function TextSearch({ name, setName }) {
  return (
    <div className="my-4">
      <input
        type="text"
        placeholder="Skriv in ett namn..."
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="border-2 border-gray-300 p-2 rounded-lg focus:outline-none focus:border-blue-500"
      />
    </div>
  );
}

export default TextSearch;
