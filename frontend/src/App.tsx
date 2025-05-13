import React, { useState } from 'react';
import { FileUpload } from './components/FileUpload';
import { FileList } from './components/FileList';
import { FileSearch } from './components/FileSearch';
import { StorageSummary } from './components/StorageSummary';
import { File } from './types/file';

function App() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchResults, setSearchResults] = useState<File[]>([]);
  const [hasSearched, setHasSearched] = useState(false);

  const handleUploadSuccess = () => {
    setRefreshKey((prev) => prev + 1);
    // Reset search state after an upload
    setSearchResults([]);
    setHasSearched(false);
  };

  const handleSearchResults = (files: File[]) => {
    setSearchResults(files);
    setHasSearched(true);
  };

  const handleClearFilters = () => {
    // Reset search state to show all files
    setSearchResults([]);
    setHasSearched(false);
    // Increment refresh key to ensure FileList refreshes with all files
    setRefreshKey((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          <h1 className="text-3xl font-bold text-gray-900">Abnormal Security - File Hub</h1>
          <p className="mt-1 text-sm text-gray-500">File management system</p>
        </div>
      </header>
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <StorageSummary />
        <FileSearch onResults={handleSearchResults} onClearFilters={handleClearFilters} />
        <div className="px-4 py-6 sm:px-0">
          <div className="space-y-6">
            <div className="bg-white shadow sm:rounded-lg">
              <FileUpload onUploadSuccess={handleUploadSuccess} />
            </div>
            <div className="bg-white shadow sm:rounded-lg">
              <FileList 
                key={refreshKey} 
                files={hasSearched ? searchResults : undefined} 
              />
            </div>
          </div>
        </div>
      </main>
      <footer className="bg-white shadow mt-8">
        <div className="max-w-7xl mx-auto py-4 px-4 sm:px-6 lg:px-8">
          <p className="text-center text-sm text-gray-500">© 2024 File Hub. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}

export default App;
