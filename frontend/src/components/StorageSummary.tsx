import React from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { formatFileSize } from '../utils/format';

interface StorageSummaryData {
  total_file_size: number;
  deduplicated_storage: number;
  storage_saved: number;
}

export const StorageSummary: React.FC = () => {
  const { data, isLoading, error } = useQuery<StorageSummaryData, Error>({
    queryKey: ['storageSummary'],
    queryFn: async (): Promise<StorageSummaryData> => {
      const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';
      const response = await axios.get(`${API_URL}/files/storage-summary/`);
      return response.data;
    }
  });

  if (isLoading) return (
    <div className="p-6 bg-white shadow rounded-lg mb-6">
      <h2 className="text-xl font-semibold mb-4">Storage Summary</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-24 mb-2"></div>
            <div className="h-6 bg-gray-200 rounded w-16"></div>
          </div>
        ))}
      </div>
    </div>
  );

  if (error) return (
    <div className="p-6 bg-white shadow rounded-lg mb-6">
      <div className="bg-red-50 border-l-4 border-red-400 p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="ml-3">
            <p className="text-sm text-red-700">Failed to load storage summary. Please try again later.</p>
          </div>
        </div>
      </div>
    </div>
  );

  const savingsPercentage = data
    ? ((data.storage_saved / data.total_file_size) * 100).toFixed(1)
    : '0';

  return (
    <div className="p-6 bg-white shadow rounded-lg mb-6">
      <h2 className="text-xl font-semibold mb-4">Storage Summary</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-500">Total File Size</p>
          <p className="text-lg font-bold text-gray-900">{formatFileSize(data?.total_file_size ?? 0)}</p>
        </div>
        <div className="p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-500">Deduplicated Storage</p>
          <p className="text-lg font-bold text-gray-900">{formatFileSize(data?.deduplicated_storage ?? 0)}</p>
        </div>
        <div className="p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-500">Storage Saved</p>
          <p className="text-lg font-bold text-gray-900">{formatFileSize(data?.storage_saved ?? 0)}</p>
          <p className="text-sm text-green-600">({savingsPercentage}% reduction)</p>
        </div>
      </div>
    </div>
  );
};
