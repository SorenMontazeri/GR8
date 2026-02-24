import { useState } from 'react'
import './App.css'
import SearchButton from './components/Searchbutton'
import TextSearch from './components/TextSearch.jsx'
import Image from './components/Image.jsx'

function App() {
  const [name, setName] = useState('')
  const [selectedName, setSelectedName] = useState('')

  const handleSearch = () => {
    const trimmed = name.trim()
    if (!trimmed) return
    setSelectedName(trimmed)
  }

  return (
    <div className="App flex flex-col items-center justify-center min-h-screen">
      <h1 className="text-3xl font-bold text-gray-800">GR8</h1>

      <TextSearch name={name} setName={setName} />
      <SearchButton onSearch={handleSearch} />
      <Image name={selectedName} />

    </div>
  )
}

export default App
