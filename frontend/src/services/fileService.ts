import axios from 'axios';
import { File as FileType } from '../types/file';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

export const fileService = {
  async uploadFile(file: File): Promise<FileType> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('original_filename', file.name);
    formData.append('file_type', file.name.split('.').pop() || '');

    const response = await axios.post(`${API_URL}/files/`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  async getFiles(): Promise<FileType[]> {
    const response = await axios.get(`${API_URL}/files/`);
    return response.data.items || [];
  },

  async deleteFile(id: string): Promise<void> {
    await axios.delete(`${API_URL}/files/${id}/`);
  },

  async downloadFile(fileId: string, filename: string): Promise<void> {
    const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';
    const downloadUrl = `${API_URL}/files/${fileId}/download/`;
    const response = await axios.get(downloadUrl, {
      responseType: 'blob',
    });
  
    const blob = new Blob([response.data]);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
  

  async searchFiles(params: {
    query?: string;
    file_type?: string;
    min_size?: number;
    max_size?: number;
    start_date?: string;
    end_date?: string;
    page?: number;
    page_size?: number;
  }): Promise<FileType[]> {
    // 1) Remap FE keys → BE keys
    const mapped: Record<string, any> = {};
    if (params.query)       mapped.filename       = params.query;
    if (params.file_type)   mapped.file_extension = params.file_type;
    if (params.min_size != null) mapped.min_size  = params.min_size;
    if (params.max_size != null) mapped.max_size  = params.max_size;
    if (params.start_date)  mapped.start_date    = params.start_date;
    if (params.end_date)    mapped.end_date      = params.end_date;
    if (params.page)        mapped.page          = params.page;
    if (params.page_size)   mapped.page_size     = params.page_size;

    try {
      // 2) Call the unified list endpoint
      const response = await axios.get(`${API_URL}/files/`, { params: mapped });

      // 3) Return just the items array (FileType[])
      return response.data.items || [];
    } catch (error: any) {
      if (axios.isAxiosError(error) && error.response) {
        // Flatten any field‐level arrays into one message (optional)
        const resp = error.response.data;
        let msg = 'Failed to perform search.';
        if (resp && typeof resp === 'object') {
          msg = Object.values(resp)
            .filter(Array.isArray)
            .flat()
            .map(String)
            .join('\n') || msg;
        }
        throw new Error(msg);
      }
      throw error;
    }
  },
};