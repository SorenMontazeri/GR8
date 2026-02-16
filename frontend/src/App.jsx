import { useEffect, useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'
import Search from './components/SearchButton'

function App() {
  return (
    <div className="App">
      <h1 className="text-3xl font-bold text-center text-gray-800">GR8</h1>
      <Search />
    </div>
   )
}

export default App
