from django.test import TestCase
from datetime import datetime, date, timedelta
import uuid
import os
from django.core.files.uploadedfile import SimpleUploadedFile
from freezegun import freeze_time
from django.conf import settings

from files.services.search_service import SearchService
from files.models import File


class TestSearchService(TestCase):
    
    def setUp(self):
        """Set up test data in a real database"""
        self.search_service = SearchService()
        
        # Use helper method to create test files with diverse characteristics
        self._create_test_files()
    
    def _create_test_files(self):
        """Create a diverse set of test files to validate search filtering"""
        # File metadata with varied properties for comprehensive filter testing
        files_data = [
            # Format: (name, ext, size_kb, created_days_ago)
            ("document", "txt", 1, 60),         # Small text file from 60 days ago
            ("report", "pdf", 1024, 30),        # Medium PDF from 30 days ago
            ("image", "png", 10240, 15),        # Large image from 15 days ago
            ("spreadsheet", "xlsx", 2048, 7),   # Medium spreadsheet from 7 days ago
            ("presentation", "pptx", 5120, 3),  # Large presentation from 3 days ago
            ("archive", "zip", 20480, 1),       # Very large archive from yesterday
            ("code_sample", "py", 5, 45),       # Tiny Python file from 45 days ago
            ("data", "json", 100, 10),          # Small JSON from 10 days ago
            ("instructions", "txt", 2, 5),      # Tiny text file from 5 days ago (second txt file)
        ]
        
        self.created_files = {}
        
        # Create each file with unique properties
        for i, (name, ext, size_kb, days_ago) in enumerate(files_data):
            filename = f"{name}.{ext}"
            # Generate a unique hash
            file_hash = f"hash{i+1:02d}" * 4  # Create unique hash (64 chars)
            
            # Create base file entry
            file_obj = File.objects.create(
                file_hash=file_hash,
                original_filename=filename,
                file_type=ext,
                size=size_kb * 1024,  # Convert KB to bytes
                ref_count=1 + (i % 3),  # Vary reference count (1-3)
                # We'll set dates separately below
            )
            
            # Create an actual dummy file to save
            dummy_file = SimpleUploadedFile(filename, f"content for {filename}".encode())
            file_obj.file.save(filename, dummy_file, save=False)
            
            # Use days_ago to create varied upload dates with timedelta
            base_date = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
            upload_date = base_date - timedelta(days=days_ago)
            file_obj.uploaded_at = upload_date
            file_obj.save()
            
            # Store for easy reference in tests
            self.created_files[name] = file_obj
        
        # Create a deleted file (shouldn't appear in searches)
        self.deleted_file = File.objects.create(
            file_hash="hashXX" * 4,
            original_filename="deleted.doc", 
            file_type="doc",
            size=500 * 1024,  # 500 KB
            ref_count=0,
            is_deleted=True
        )
        dummy_file = SimpleUploadedFile("deleted.doc", b"dummy content")
        self.deleted_file.file.save("deleted.doc", dummy_file, save=True)
    
    def tearDown(self):
        """Clean up test files"""
        for file_obj in File.objects.all():
            if file_obj.file:
                file_obj.file.delete()
        File.objects.all().delete()
    
    def test_search_with_no_filters_returns_all_active_files(self):
        # Arrange
        params = {"page": 1, "page_size": 20}  # Ensure we get all files
        
        # Act - Use the real service with a real database
        result = self.search_service.search(params)
        
        # Assert - We should get all non-deleted files
        self.assertEqual(result["total"], 9)  # 9 active files
        self.assertEqual(len(result["items"]), 9)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 20)
        
        # Verify deleted files don't appear
        filenames = [item["original_filename"] for item in result["items"]]
        self.assertNotIn("deleted.doc", filenames)
        
        # Verify all created files are present
        for name, file_obj in self.created_files.items():
            self.assertIn(f"{name}.{file_obj.file_type}", filenames)
    
    def test_search_with_filename_filter(self):
        # First, ensure we have a file with "doc" in the name
        all_files = list(self.created_files.values())
        doc_files = [f for f in all_files if "doc" in f.original_filename.lower()]
        self.assertGreater(len(doc_files), 0, "Need at least one file with 'doc' in the name")
        
        # Get expected files based on actual filter behavior
        expected_doc_filenames = [f.original_filename for f in doc_files]
        
        params = {"filename": "doc", "page": 1, "page_size": 10}
        
        # Act - Using real database query with substring matching
        result = self.search_service.search(params)
        
        # Get actual filenames
        actual_filenames = [item["original_filename"] for item in result["items"]]
        
        # Print debug info
        print(f"Filename filter 'doc' test:")
        print(f"Expected files: {expected_doc_filenames}")
        print(f"Actual files: {actual_filenames}")
        
        # Assert - Match count should equal expected doc files
        self.assertEqual(result["total"], len(doc_files))
        self.assertEqual(len(result["items"]), len(doc_files))
        
        # Verify all expected files are in results
        for filename in expected_doc_filenames:
            self.assertIn(filename, actual_filenames)
        
        # Test exact match with full word
        params = {"filename": "document", "page": 1, "page_size": 10}
        result = self.search_service.search(params)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["original_filename"], "document.txt")
        
        # Test case insensitivity with mixed case
        params = {"filename": "DoCuMeNt", "page": 1, "page_size": 10}
        result = self.search_service.search(params)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["original_filename"], "document.txt")
    
    def test_search_with_extension_filter(self):
        # Test with txt extension - should find both document.txt and instructions.txt
        params = {"file_extension": "txt", "page": 1, "page_size": 10}
        result = self.search_service.search(params)
        
        # Assert all text files are found
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["items"]), 2)
        
        # Verify both text files are returned
        filenames = [item["original_filename"] for item in result["items"]]
        self.assertIn("document.txt", filenames)
        self.assertIn("instructions.txt", filenames)
        
        # Test with pdf extension
        params = {"file_extension": "pdf", "page": 1, "page_size": 10}
        result = self.search_service.search(params)
        
        # Assert exactly one PDF file is found
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["original_filename"], "report.pdf")
        
        # Test case insensitivity
        params = {"file_extension": "PNG", "page": 1, "page_size": 10}  # Uppercase extension
        result = self.search_service.search(params)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["original_filename"], "image.png")
    
    def test_search_with_min_size_filter(self):
        # Arrange - 5MB minimum size filter
        min_size = 5 * 1024 * 1024  # 5 MB
        params = {"min_size": min_size, "page": 1, "page_size": 10}
        
        # Act - using real database query
        result = self.search_service.search(params)
        
        # Files larger than 5MB: image.png (10MB), presentation.pptx (5MB), archive.zip (20MB)
        expected_large_files = ["image.png", "presentation.pptx", "archive.zip"]
        
        # Assert - Correct number of files >= 5MB found
        self.assertEqual(result["total"], len(expected_large_files))
        self.assertEqual(len(result["items"]), len(expected_large_files))
        
        # Verify all returned files meet the min size criteria
        for item in result["items"]:
            self.assertTrue(item["file_size"] >= min_size,
                          f"File {item['original_filename']} size {item['file_size']} should be >= {min_size}")
            
        # Check all expected large files are in the results
        filenames = [item["original_filename"] for item in result["items"]]
        for filename in expected_large_files:
            self.assertIn(filename, filenames)
        
        # Verify a small file is NOT in the results
        self.assertNotIn("document.txt", filenames)
    
    def test_search_with_max_size_filter(self):
        # Arrange - Files under 100KB
        max_size = 100 * 1024  # 100 KB
        params = {"max_size": max_size, "page": 1, "page_size": 10}
        
        # Act - using real database query
        result = self.search_service.search(params)
        
        # Verify count is greater than zero 
        self.assertGreater(result["total"], 0)
        self.assertGreater(len(result["items"]), 0)
        
        # At minimum, these small files should be included
        expected_small_files = ["document.txt", "instructions.txt", "code_sample.py"]
        
        # Verify all returned files meet the max size criteria
        for item in result["items"]:
            self.assertTrue(item["file_size"] <= max_size,
                          f"File {item['original_filename']} size {item['file_size']} should be <= {max_size}")
            
        # Check all expected small files are in the results
        filenames = [item["original_filename"] for item in result["items"]]
        for filename in expected_small_files:
            self.assertIn(filename, filenames)
            
        # Log all matching files for debugging
        print(f"Files matching max_size={max_size}: {filenames}")
            
        # Verify a large file is NOT in the results
        self.assertNotIn("image.png", filenames)

    def test_search_with_size_range_filter(self):
        # Arrange - Files between 100KB and 5MB
        min_size = 100 * 1024      # 100 KB
        max_size = 5 * 1024 * 1024  # 5 MB
        params = {"min_size": min_size, "max_size": max_size, "page": 1, "page_size": 10}
        
        # Act - using real database query
        result = self.search_service.search(params)
        
        # Verify we have results
        self.assertGreater(result["total"], 0)
        self.assertGreater(len(result["items"]), 0)
        
        # At minimum, these medium-sized files should be included
        expected_medium_files = ["data.json", "report.pdf", "spreadsheet.xlsx"]
        
        # Verify all returned files meet the size range criteria
        for item in result["items"]:
            file_size = item["file_size"]
            self.assertTrue(min_size <= file_size <= max_size,
                          f"File {item['original_filename']} size {file_size} should be between {min_size} and {max_size}")
        
        # Get filenames from the results for verification
        filenames = [item["original_filename"] for item in result["items"]]
        print(f"Files between {min_size/1024}KB and {max_size/1024/1024}MB: {filenames}")
        
        # Check all expected medium files are in the results
        for filename in expected_medium_files:
            self.assertIn(filename, filenames)
            
        # Verify files outside the range are NOT in the results
        self.assertNotIn("document.txt", filenames)  # Too small
        self.assertNotIn("archive.zip", filenames)   # Too large
    
    @freeze_time("2025-05-01")  # Freeze time to a fixed date
    def test_search_with_start_date_filter(self):
        # Arrange - Use the existing files we created with different upload dates
        # Sort files by upload date
        all_files = list(self.created_files.values())
        sorted_files = sorted(all_files, key=lambda f: f.uploaded_at)
        
        # Get the upload date of a file in the middle of our date range to use as filter
        # This ensures we'll have some files before and some after
        middle_index = len(sorted_files) // 2
        middle_file = sorted_files[middle_index]
        start_date = middle_file.uploaded_at.date()
        
        # Find files that should match our filter (on or after the start date)
        expected_files = [f for f in sorted_files if f.uploaded_at.date() >= start_date]
        
        # Check that we have both matching and non-matching files
        self.assertGreater(len(expected_files), 0, "Need at least one file matching the start date")
        self.assertLess(len(expected_files), len(all_files), "Need at least one file not matching the start date")
        
        params = {"start_date": start_date, "page": 1, "page_size": 20}
        
        # Act
        result = self.search_service.search(params)
        
        # Assert
        self.assertEqual(result["total"], len(expected_files))
        self.assertEqual(len(result["items"]), len(expected_files))
        
        # Get all the filenames that should match our filter
        expected_filenames = [f.original_filename for f in expected_files]
        actual_filenames = [item["original_filename"] for item in result["items"]]
        
        # Print debug info
        print(f"Start date filter: {start_date}")
        print(f"Expected files: {expected_filenames}")
        print(f"Actual files: {actual_filenames}")
        
        # Verify all returned files meet the criteria
        for item in result["items"]:
            # Handle the uploaded_at field which could be a datetime object or string
            uploaded_at = item["uploaded_at"]
            if isinstance(uploaded_at, str):
                uploaded_date = datetime.fromisoformat(uploaded_at).date()
            else:
                uploaded_date = uploaded_at.date()
                
            self.assertTrue(uploaded_date >= start_date,
                          f"File {item['original_filename']} uploaded on {uploaded_date} should be on or after {start_date}")
        
        # Check that all expected files are in the results
        for filename in expected_filenames:
            self.assertIn(filename, actual_filenames)
        
    @freeze_time("2025-05-01")  # Freeze time to a fixed date
    def test_search_with_end_date_filter(self):
        # Arrange - Use the existing files we created with different upload dates
        # Sort files by upload date
        all_files = list(self.created_files.values())
        sorted_files = sorted(all_files, key=lambda f: f.uploaded_at)
        
        # Get the upload date of a file in the middle of our date range
        middle_index = len(sorted_files) // 2
        middle_file = sorted_files[middle_index]
        end_date = middle_file.uploaded_at.date()
        
        # Find files that should match our filter (on or before the end date)
        expected_files = [f for f in sorted_files if f.uploaded_at.date() <= end_date]
        
        # Ensure we have a good test case with both matching and non-matching files
        self.assertGreater(len(expected_files), 0, "Need at least one file matching the end date")
        self.assertLess(len(expected_files), len(all_files), "Need at least one file not matching the end date")
        
        # Use the middle file's date from earlier
        params = {"end_date": end_date, "page": 1, "page_size": 20}
        
        # Act - Using real database query
        result = self.search_service.search(params)
        
        # Assert - Should match our expected files count
        self.assertEqual(result["total"], len(expected_files))
        self.assertEqual(len(result["items"]), len(expected_files))
        
        # Get all the filenames that should match our filter
        expected_filenames = [f.original_filename for f in expected_files]
        actual_filenames = [item["original_filename"] for item in result["items"]]
        
        # Print debug info
        print(f"End date filter: {end_date}")
        print(f"Expected files: {expected_filenames}")
        print(f"Actual files: {actual_filenames}")
        
        # Verify all returned files meet the criteria
        for item in result["items"]:
            # Handle the uploaded_at field which could be a datetime object or string
            uploaded_at = item["uploaded_at"]
            if isinstance(uploaded_at, str):
                uploaded_date = datetime.fromisoformat(uploaded_at).date()
            else:
                uploaded_date = uploaded_at.date()
                
            self.assertTrue(uploaded_date <= end_date,
                          f"File {item['original_filename']} uploaded on {uploaded_date} should be on or before {end_date}")
        
        # Check that all expected files are in the results
        for filename in expected_filenames:
            self.assertIn(filename, actual_filenames)
    
    @freeze_time("2025-05-01")  # Freeze time to a fixed date
    def test_search_with_date_range_filter(self):
        # Arrange - Use the existing files we created with different upload dates
        # Sort files by upload date
        all_files = list(self.created_files.values())
        sorted_files = sorted(all_files, key=lambda f: f.uploaded_at)
        
        # Ensure we have enough files for a proper date range test
        self.assertGreaterEqual(len(sorted_files), 3, "Need at least 3 files for date range test")
        
        # Divide files into three parts to get dates that will include only the middle section
        first_third_index = len(sorted_files) // 3
        last_third_index = first_third_index * 2
        
        # Use first third's last file as start date
        start_date = sorted_files[first_third_index].uploaded_at.date()
        
        # Use last third's first file as end date
        end_date = sorted_files[last_third_index].uploaded_at.date()
        
        # Make sure start_date is before end_date (in case of weird ordering)
        if start_date > end_date:
            start_date, end_date = end_date, start_date
            
        # Find files that should match our date range filter
        expected_files = [f for f in sorted_files if start_date <= f.uploaded_at.date() <= end_date]
        
        # Check that we have both matching and non-matching files
        self.assertGreater(len(expected_files), 0, "Need at least one file in the date range")
        self.assertLess(len(expected_files), len(all_files), "Need at least one file outside the date range")
        
        params = {"start_date": start_date, "end_date": end_date, "page": 1, "page_size": 20}
        
        # Act - Using real database query
        result = self.search_service.search(params)
        
        # Get expected and actual filenames
        expected_filenames = [f.original_filename for f in expected_files]
        actual_filenames = [item["original_filename"] for item in result["items"]]
        
        # Print debug info
        print(f"Date range filter: {start_date} to {end_date}")
        print(f"Expected files: {expected_filenames}")
        print(f"Actual files: {actual_filenames}")
        
        # Assert - Should match our expected count
        self.assertEqual(result["total"], len(expected_files))
        self.assertEqual(len(result["items"]), len(expected_files))
        
        # Verify all returned files meet the criteria
        for item in result["items"]:
            # Handle the uploaded_at field which could be a datetime object or string
            uploaded_at = item["uploaded_at"]
            if isinstance(uploaded_at, str):
                uploaded_date = datetime.fromisoformat(uploaded_at).date()
            else:
                uploaded_date = uploaded_at.date()
                
            self.assertTrue(start_date <= uploaded_date <= end_date,
                          f"File {item['original_filename']} uploaded on {uploaded_date} should be between {start_date} and {end_date}")
        
        # Check that all expected files are in the results
        for filename in expected_filenames:
            self.assertIn(filename, actual_filenames)

    def test_search_with_pagination(self):
        # Arrange - Define pagination parameters
        page_size = 2
        page = 2
        
        # Get total count directly from database to compare with API response
        total_files = File.objects.filter(is_deleted=False).count()
        
        # Ensure we have enough files for pagination testing
        self.assertGreaterEqual(total_files, (page * page_size), 
                               f"Need at least {page * page_size} files for pagination test with page {page} and page_size {page_size}")
        
        params = {"page": page, "page_size": page_size}
        
        # Act - Using real database query
        result = self.search_service.search(params)
        
        # Get filenames from result
        actual_filenames = [item["original_filename"] for item in result["items"]]
        
        # Assert - Pagination details
        self.assertEqual(result["page"], page)
        self.assertEqual(result["page_size"], page_size)
        self.assertEqual(result["total"], total_files)
        self.assertEqual(len(result["items"]), page_size)
        
        # Verify we have the expected number of unique items
        self.assertEqual(len(set(actual_filenames)), page_size, "Should have exactly page_size unique files")
        
        # Now check page 1 to ensure different results
        page1_params = {"page": 1, "page_size": page_size}
        page1_result = self.search_service.search(page1_params)
        page1_filenames = [item["original_filename"] for item in page1_result["items"]]
        
        # Verify we get different results for different pages
        # At least one file should be different between pages
        self.assertTrue(set(actual_filenames) != set(page1_filenames), 
                       "Page 2 should return different files than page 1")
        
        # Print debug info
        print(f"Pagination test: total files={total_files}, page={page}, page_size={page_size}")
        print(f"Page 1 files: {page1_filenames}")
        print(f"Page 2 files: {actual_filenames}")
            
    def test_search_with_combined_filters(self):
        # Arrange - Use existing files to test combined filtering
        all_files = list(self.created_files.values())
        
        # We'll use multiple filters together: filename and max_size
        # First, find files with 'report' in their name
        report_files = [f for f in all_files if 'report' in f.original_filename.lower()]
        
        # Ensure we have at least one file with 'report' in the name
        if not report_files:
            # Create a test file with 'report' in name if none exists
            report_file = SimpleUploadedFile(
                name="test_report.txt",
                content=b"This is a test report file",
                content_type="text/plain"
            )
            file_obj = File.objects.create(
                id=uuid.uuid4(),
                file=report_file,
                original_filename="test_report.txt",
                size=len(b"This is a test report file"),
                content_type="text/plain",
                uploaded_at=datetime.now() - timedelta(days=10)
            )
            self.created_files["test_report.txt"] = file_obj
            report_files.append(file_obj)
        
        # Find small report files (under 5MB)
        max_size = 5 * 1024 * 1024  # 5 MB
        small_report_files = [f for f in report_files if f.size <= max_size]
        min_size = 500 * 1024  # 500KB
        max_size = 5 * 1024 * 1024  # 5MB
        small_report_files = [f for f in report_files if min_size <= f.size <= max_size]
        
        # Ensure we have at least one small report file
        self.assertGreater(len(small_report_files), 0, "Need at least one small report file for combined filtering")
        
        # Set the filename filter to 'report'
        filename = "report"
        
        # Find files that should match all criteria
        expected_files = [f for f in report_files if min_size <= f.size <= max_size]
        
        params = {"filename": filename, "min_size": min_size, "max_size": max_size, "page": 1, "page_size": 10}
        
        # Act - Using real database with combined filters
        result = self.search_service.search(params)
        
        # Get expected and actual filenames
        expected_filenames = [f.original_filename for f in expected_files]
        actual_filenames = [item["original_filename"] for item in result["items"]]
        
        # Print debug info
        print(f"Combined filters test: filename={filename}, min_size={min_size/1024}KB, max_size={max_size/1024/1024}MB")
        print(f"Expected files: {expected_filenames}")
        print(f"Actual files: {actual_filenames}")
        
        # Assert - Should match our expected count
        self.assertEqual(result["total"], len(expected_files))
        self.assertEqual(len(result["items"]), len(expected_files))
        
        # Verify all returned files meet all criteria
        for item in result["items"]:
            self.assertIn(filename, item["original_filename"].lower())  # filename filter
            self.assertTrue(min_size <= item["file_size"] <= max_size)  # size range filter
            
        # Check that all expected files are in the results
        for filename in expected_filenames:
            self.assertIn(filename, actual_filenames)
            
    def test_search_with_empty_results(self):
        # Arrange - Search for a filename that definitely won't match anything
        nonexistent_filename = "this-file-does-not-exist-with-random-suffix-xyz-123"
        
        # Verify this filename truly doesn't exist in our database
        existing_files = File.objects.filter(original_filename__icontains=nonexistent_filename)
        self.assertEqual(existing_files.count(), 0, f"Test prerequisite: Filename '{nonexistent_filename}' should not exist")
        
        params = {"filename": nonexistent_filename, "page": 1, "page_size": 10}
        
        # Act - Using real database with filters that won't match anything
        result = self.search_service.search(params)
        
        # Assert - No results should be found
        self.assertEqual(result["total"], 0)
        self.assertEqual(len(result["items"]), 0)
        self.assertEqual(result["page"], 1)  # Should still return requested page number
        self.assertEqual(result["page_size"], 10)  # Should still return requested page size
        
        # Print debug info
        print(f"Empty results test: search for '{nonexistent_filename}' returned {result['total']} results")
        
        # Verify search still works after getting empty results
        # This ensures the service handles empty results gracefully
        new_params = {"page": 1, "page_size": 10}  # No filters should return all files
        new_result = self.search_service.search(new_params)
        self.assertGreater(new_result["total"], 0)  # Should return all our non-deleted files
            
    def test_search_with_default_pagination(self):
        # Arrange - Just search with no explicit pagination params
        params = {}
        
        # Get actual file count from database
        total_files = File.objects.filter(is_deleted=False).count()
        
        # Default pagination parameters
        expected_page = 1
        expected_page_size = 10
        
        # Act - Using real database with default pagination
        result = self.search_service.search(params)
        
        # Get filenames from result
        actual_filenames = [item["original_filename"] for item in result["items"]]
        print(f"Default pagination test: total files={total_files}")
        print(f"Files on page 1: {actual_filenames}")
        
        # Assert - Default pagination should be applied
        self.assertEqual(result["page"], expected_page)
        
        # Determine the actual default page_size used by the search service
        actual_page_size = result["page_size"]
        print(f"Default page_size used by search_service: {actual_page_size}")
        
        self.assertEqual(result["total"], total_files)
        
        # Should return all items if total < page_size, otherwise just page_size
        expected_returned = min(total_files, actual_page_size)
        self.assertEqual(len(result["items"]), expected_returned)  
        
        # Verify we have results if there are files in the database
        if total_files > 0:
            self.assertGreater(len(result["items"]), 0, "Should return at least one file if database has files")
