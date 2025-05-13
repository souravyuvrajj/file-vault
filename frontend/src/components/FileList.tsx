import React, { useState } from 'react';
import { fileService } from '../services/fileService';
import { File } from '../types/file';
import {
  DocumentIcon,
  TrashIcon,
  ArrowDownTrayIcon,
  DocumentTextIcon,
  PhotoIcon,
  VideoCameraIcon,
  MusicalNoteIcon,
  CodeBracketIcon,
  ArchiveBoxIcon,
} from '@heroicons/react/24/outline';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { formatFileSize } from '../utils/format';

interface FileListProps {
  files?: File[];
}

interface FileToDelete {
  id: string;
  name: string;
}

const getFileIcon = (fileType: string) => {
  const type = fileType.toLowerCase();
  if (type.match(/^image\//)) return PhotoIcon;
  if (type.match(/^video\//)) return VideoCameraIcon;
  if (type.match(/^audio\//)) return MusicalNoteIcon;
  if (type.match(/^text\/(plain|html|css|javascript|typescript)/)) return CodeBracketIcon;
  if (type.match(/^application\/(zip|x-rar|x-7z-compressed)/)) return ArchiveBoxIcon;
  if (type.match(/^application\/(pdf|msword|vnd.openxmlformats)/)) return DocumentTextIcon;
  return DocumentIcon;
};

export const FileList: React.FC<FileListProps> = ({ files: propFiles }) => {
  const queryClient = useQueryClient();
  const [fileToDelete, setFileToDelete] = useState<FileToDelete | null>(null);
  const [downloadingFiles, setDownloadingFiles] = useState<Set<string>>(new Set());
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data: files, isLoading, error } = useQuery<File[]>({
    queryKey: ['files'],
    queryFn: fileService.getFiles,
    enabled: !propFiles,
  });

  const filesToDisplay = propFiles || files;

  const deleteMutation = useMutation({
    mutationFn: fileService.deleteFile,
    onMutate: async (fileId) => {
      await queryClient.cancelQueries({ queryKey: ['files'] });
      const previousFiles = queryClient.getQueryData<File[]>(['files']);
      if (previousFiles) {
        queryClient.setQueryData<File[]>(['files'], previousFiles.filter(file => file.id !== fileId));
      }
      setFileToDelete(null);
      return { previousFiles };
    },
    onError: (err, variables, context) => {
      if (context?.previousFiles) {
        queryClient.setQueryData(['files'], context.previousFiles);
      }
      setDeleteError('Failed to delete file. Please try again.');
      console.error('Delete error:', err);
    },
    onSuccess: () => {
      setDeleteError(null);
      // Invalidate both queries so that the files list and storage summary re-fetch new data.
      queryClient.invalidateQueries({ queryKey: ['files'] });
      queryClient.invalidateQueries({ queryKey: ['storageSummary'] });
    },
    onSettled: () => {
      // Ensure both queries are refetched after the mutation settles.
      queryClient.invalidateQueries({ queryKey: ['files'] });
      queryClient.invalidateQueries({ queryKey: ['storageSummary'] });
    },
  });  

  const handleDelete = async (id: string) => {
    try {
      setDeleteError(null);
      await deleteMutation.mutateAsync(id);
    } catch (err) {
      // Error handling is done in onError callback
    }
  };

  const handleDownload = async (fileId: string, filename: string) => {
    setDownloadingFiles(prev => new Set(prev).add(filename));
    try {
      await fileService.downloadFile(fileId, filename);
    } catch (err) {
      console.error('Download error:', err);
    } finally {
      setDownloadingFiles(prev => {
        const newSet = new Set(prev);
        newSet.delete(filename);
        return newSet;
      });
    }
  };  

  if (isLoading) {
    return (
      <div className="p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Uploaded Files</h2>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse flex items-center space-x-4 py-4">
              <div className="rounded-full bg-gray-200 h-10 w-10"></div>
              <div className="flex-1">
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                <div className="space-y-2 mt-2">
                  <div className="h-3 bg-gray-200 rounded w-1/4"></div>
                  <div className="h-3 bg-gray-200 rounded w-1/2"></div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border-l-4 border-red-400 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700">Failed to load files. Please try again later.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">Uploaded Files</h2>
      {!filesToDisplay || filesToDisplay.length === 0 ? (
        <div className="text-center py-12">
          <DocumentIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">
            {propFiles !== undefined ? 'No search results found' : 'No files'}
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            {propFiles !== undefined 
              ? 'Try adjusting your search criteria' 
              : 'Get started by uploading a file'}
          </p>
        </div>
      ) : (
        <>
          <div className="mt-6 flow-root">
            <ul className="-my-5 divide-y divide-gray-200">
              {filesToDisplay.map((file) => {
                const FileIcon = getFileIcon(file.file_type);
                const isDownloading = downloadingFiles.has(file.original_filename);
                return (
                  <li key={file.id} className="py-4">
                    <div className="flex items-center space-x-4">
                      <div className="flex-shrink-0">
                        <FileIcon className="h-8 w-8 text-gray-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {file.original_filename}
                        </p>
                        <p className="text-sm text-gray-500">
                        {file.file_type} • {formatFileSize(file.file_size)}
                        </p>
                        <p className="text-sm text-gray-500">Refs: {file.ref_count}</p>
                        <p className="text-sm text-gray-500">
                          Uploaded {new Date(file.uploaded_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex space-x-2">
                        <button
                          onClick={() => handleDownload(file.id, file.original_filename)}
                          disabled={isDownloading}
                          className="inline-flex items-center px-3 py-2 border border-transparent shadow-sm text-sm leading-4 font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50"
                        >
                          {isDownloading ? (
                            <>
                              <svg className="animate-spin h-4 w-4 mr-1" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                              </svg>
                              Downloading...
                            </>
                          ) : (
                            <>
                              <ArrowDownTrayIcon className="h-4 w-4 mr-1" />
                              Download
                            </>
                          )}
                        </button>
                        <button
                          onClick={() => setFileToDelete({ id: file.id, name: file.original_filename })}
                          disabled={deleteMutation.isPending}
                          className="inline-flex items-center px-3 py-2 border border-transparent shadow-sm text-sm leading-4 font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50"
                        >
                          <TrashIcon className="h-4 w-4 mr-1" />
                          Delete
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Delete Confirmation Modal */}
          {fileToDelete && (
            <div className="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4">
              <div className="bg-white rounded-lg max-w-md w-full p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Delete File</h3>
                <p className="text-sm text-gray-500">
                  Are you sure you want to delete "{fileToDelete.name}"? This action cannot be undone.
                </p>
                <div className="mt-6 flex justify-end space-x-3">
                  <button
                    onClick={() => setFileToDelete(null)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => handleDelete(fileToDelete.id)}
                    disabled={deleteMutation.isPending}
                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50"
                  >
                    {deleteMutation.isPending ? (
                      <>
                        <svg className="animate-spin h-4 w-4 mr-1" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Deleting...
                      </>
                    ) : (
                      'Delete'
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};