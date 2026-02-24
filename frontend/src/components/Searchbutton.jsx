import { useState } from 'react'

function SearchButton({ onSearch }) {
  const [clicked, setClicked] = useState(false)

  const handleSave = () => {
    onSearch()
    setClicked(true)
  }

  return (
    <div>
      <button
        className="px-4 py-2 bg-blue-500 text-white rounded shadow"
        onClick={handleSave}
        style={{ backgroundColor: clicked ? 'green' : '#3b82f6' }}
      >
        {clicked ? 'Sök igen' : 'Hämta bild'}
      </button>
    </div>
  )
}

export default SearchButton
