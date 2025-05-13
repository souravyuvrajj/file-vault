// src/components/FileSearch.tsx
import React, { useState } from 'react';
import { fileService } from '../services/fileService';
import { File } from '../types/file';

const MULTIPLIERS: Record<'B' | 'KB' | 'MB' | 'GB', number> = {
  B: 1,
  KB: 1024,
  MB: 1024 ** 2,
  GB: 1024 ** 3,
}

interface SearchFilters {
  query: string;
  file_type: string;
  min_size: number | '';
  max_size: number | '';
  start_date: string;
  end_date: string;
  min_size_unit: keyof typeof MULTIPLIERS
  max_size_unit: keyof typeof MULTIPLIERS
}



interface FileSearchProps {
  onResults: (files: File[]) => void;
  onClearFilters: () => void;
}

export const FileSearch: React.FC<FileSearchProps> = ({ onResults, onClearFilters }) => {
  const [filters, setFilters] = useState<SearchFilters>({
    query: '',
    file_type: '',
    min_size: '',
    max_size: '',
    start_date: '',
    end_date: '',
    min_size_unit: 'MB',
    max_size_unit: 'MB',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFilters((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const convertToBytes = (size: number | '', unit: string): number | undefined => {
    if (size === '') return undefined;
    const multipliers: { [key: string]: number } = {
      B: 1,
      KB: 1024,
      MB: 1024 * 1024,
      GB: 1024 * 1024 * 1024,
    };
    return size * multipliers[unit];
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    
     // 1) coerce to numbers
    const rawMin = filters.min_size === '' ? undefined : Number(filters.min_size)
    const rawMax = filters.max_size === '' ? undefined : Number(filters.max_size)

    // 2) convert to bytes
    const minSizeBytes =
      rawMin != null
        ? rawMin * MULTIPLIERS[filters.min_size_unit]!
        : undefined
    const maxSizeBytes =
      rawMax != null
        ? rawMax * MULTIPLIERS[filters.max_size_unit]!
        : undefined

    // 3) require at least one filter
    const hasAny =
    filters.query.trim() !== '' ||
    filters.file_type.trim() !== '' ||
    minSizeBytes != null ||
    maxSizeBytes != null ||
    filters.start_date !== '' ||
    filters.end_date !== ''

    if (!hasAny) {
      setError('Please provide at least one search term or filter.')
      setLoading(false)
      return
    }

    try {
      // 4) build only the keys your service expects
      const params: {
        query?: string
        file_type?: string
        min_size?: number
        max_size?: number
        start_date?: string
        end_date?: string
        page?: number
        page_size?: number
    } = { page: 1, page_size: 20 };

    if (filters.query) params.query = filters.query
      if (filters.file_type) params.file_type = filters.file_type
      if (minSizeBytes != null) params.min_size = minSizeBytes
      if (maxSizeBytes != null) params.max_size = maxSizeBytes
      if (filters.start_date) params.start_date = filters.start_date
      if (filters.end_date) params.end_date = filters.end_date

    // 5) Fetch & deliver
    const results = await fileService.searchFiles(params);
    onResults(results);
    } catch (error) {
      console.error('Search error:', error);
      // Show the specific error message from the API if available
      if (error instanceof Error) {
        setError(error.message);
      } else {
        setError('Failed to perform search. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleClearFilters = () => {
    // Reset form values
    setFilters({
      query: '',
      file_type: '',
      min_size: '',
      max_size: '',
      start_date: '',
      end_date: '',
      min_size_unit: 'MB',
      max_size_unit: 'MB',
    });
    setError(null);
    
    // Notify parent component to reset search state
    onClearFilters();
  };

  return (
    <form onSubmit={handleSearch} className="p-6 bg-white shadow-md rounded-lg mb-6 border border-gray-200">
      <h2 className="text-xl font-semibold mb-5 text-gray-800 border-b pb-3">File Search</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">Filename</label>
          <input
            type="text"
            name="query"
            value={filters.query}
            onChange={handleInputChange}
            placeholder="Search by filename"
            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">File Extension</label>
          <input
            type="text"
            name="file_type"
            value={filters.file_type}
            onChange={handleInputChange}
            placeholder="e.g., pdf, jpg, docx"
            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-primary-500 focus:border-primary-500"
          />
          <p className="text-xs text-gray-500">Enter without dot (e.g. "pdf")</p>
        </div>
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">Minimum File Size</label>
          <div className="mt-1 flex">
            <input
              type="number"
              name="min_size"
              value={filters.min_size}
              onChange={handleInputChange}
              placeholder="0"
              className="block w-full border border-gray-300 rounded-l-md shadow-sm px-3 py-2 focus:ring-primary-500 focus:border-primary-500"
            />
            <select
              name="min_size_unit"
              value={filters.min_size_unit}
              onChange={handleInputChange}
              className="w-20 border-l-0 border-gray-300 rounded-r-md shadow-sm bg-gray-50 focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="B">B</option>
              <option value="KB">KB</option>
              <option value="MB">MB</option>
              <option value="GB">GB</option>
            </select>
          </div>
        </div>
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">Maximum File Size</label>
          <div className="mt-1 flex">
            <input
              type="number"
              name="max_size"
              value={filters.max_size}
              onChange={handleInputChange}
              placeholder="Unlimited"
              className="block w-full border border-gray-300 rounded-l-md shadow-sm px-3 py-2 focus:ring-primary-500 focus:border-primary-500"
            />
            <select
              name="max_size_unit"
              value={filters.max_size_unit}
              onChange={handleInputChange}
              className="w-20 border-l-0 border-gray-300 rounded-r-md shadow-sm bg-gray-50 focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="B">B</option>
              <option value="KB">KB</option>
              <option value="MB">MB</option>
              <option value="GB">GB</option>
            </select>
          </div>
        </div>
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">Upload Date (From)</label>
          <input
            type="date"
            name="start_date"
            value={filters.start_date}
            onChange={handleInputChange}
            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">Upload Date (To)</label>
          <input
            type="date"
            name="end_date"
            value={filters.end_date}
            onChange={handleInputChange}
            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
      </div>
      {error && (
        <div className="mt-4 px-4 py-3 bg-red-50 text-red-600 text-sm rounded-md border border-red-200">{error}</div>
      )}
      <div className="mt-6 flex items-center space-x-3">
        <button
          type="submit"
          disabled={loading}
          className="px-5 py-2.5 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
        >
          {loading ? (
            <div className="flex items-center">
              <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Searching...
            </div>
          ) : (
            'Search Files'
          )}
        </button>
        <button
          type="button"
          onClick={handleClearFilters}
          className="px-5 py-2.5 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2"
        >
          Clear Filters
        </button>
      </div>
    </form>
  );
};
