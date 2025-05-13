export interface File {
  id: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  uploaded_at: string;
  ref_count: number;
}