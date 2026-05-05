/* Input that the user is writing */
function TextSearch({searchString, setString}) {
  return (
    <div className="my-4">
      <input
        type="text"
        placeholder="Search for event"
        value={searchString}
        /* Updates the state in App.jsx every time the user types */
        onChange={(e) => setString(e.target.value)}
        className="text-black border-2 border-gray-300 p-2 rounded-lg focus:outline-none focus:border-yellow-500"
      />
    </div>
  );
}

export default TextSearch;
