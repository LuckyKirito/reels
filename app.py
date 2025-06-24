import json
import os
import random
import schedule
import time
import logging
from datetime import datetime, timedelta
import pytz
from instaloader import Instaloader, Post
from instagrapi import Client
import pandas as pd

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InstagramReelBot:
    def __init__(self):
        self.download_dir = "downloaded_reels"
        self.reels_file = "reels.json"
        self.used_file = "used.json"
        self.description_file = "description.xlsx"
        self.daily_limit = 5
        
        # Create directories
        os.makedirs(self.download_dir, exist_ok=True)
        
        # Initialize Instagram clients
        self.loader = Instaloader(
            download_pictures=False,
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
            post_metadata_txt_pattern=""
        )
        
        self.client = Client()
        self.setup_instagram_login()
        
        # Initialize files
        self.initialize_files()
    
    def setup_instagram_login(self):
        """Setup Instagram login credentials"""
        try:
            # Use environment variables if available, otherwise fallback to hardcoded values
            username = os.getenv('INSTAGRAM_USERNAME', 'antxlust')
            password = os.getenv('INSTAGRAM_PASSWORD', 'Roopa@143')
            
            self.client.login(username, password)
            logger.info(f"Successfully logged into Instagram with username: {username}")
        except Exception as e:
            logger.error(f"Failed to login to Instagram: {e}")
            raise
    
    def initialize_files(self):
        """Initialize JSON and Excel files if they don't exist"""
        # Initialize used.json
        if not os.path.exists(self.used_file):
            with open(self.used_file, 'w') as f:
                json.dump([], f)
        
        # Initialize description.xlsx
        if not os.path.exists(self.description_file):
            df = pd.DataFrame(columns=['URL', 'Description', 'Download_Date', 'Upload_Date'])
            df.to_excel(self.description_file, index=False)
    
    def load_json_file(self, filename):
        """Load data from JSON file"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            logger.error(f"Error reading {filename}")
            return []
    
    def save_json_file(self, filename, data):
        """Save data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_available_reels(self):
        """Get reels that haven't been used yet"""
        all_reels = self.load_json_file(self.reels_file)
        used_reels = self.load_json_file(self.used_file)
        
        available_reels = [reel for reel in all_reels if reel not in used_reels]
        return available_reels
    
    def extract_reel_info(self, url):
        """Extract reel information including description"""
        try:
            shortcode = url.rstrip('/').split('/')[-1]
            post = Post.from_shortcode(self.loader.context, shortcode)
            
            description = post.caption or "No description available"
            return {
                'url': url,
                'description': description,
                'shortcode': shortcode,
                'is_video': post.is_video
            }
        except Exception as e:
            logger.error(f"Failed to extract info from {url}: {e}")
            return None
    
    def download_reel(self, url):
        """Download a single reel"""
        try:
            reel_info = self.extract_reel_info(url)
            if not reel_info or not reel_info['is_video']:
                logger.warning(f"Skipping {url} - not a video")
                return None
            
            shortcode = reel_info['shortcode']
            post = Post.from_shortcode(self.loader.context, shortcode)
            
            # Download the reel
            self.loader.download_post(post, target=self.download_dir)
            
            # Find the downloaded video file
            video_file = None
            for file in os.listdir(self.download_dir):
                if shortcode in file and file.endswith('.mp4'):
                    video_file = os.path.join(self.download_dir, file)
                    break
            
            if video_file:
                # Save description to Excel
                self.save_description_to_excel(reel_info)
                logger.info(f"Successfully downloaded: {url}")
                return {
                    'file_path': video_file,
                    'description': reel_info['description'],
                    'url': url
                }
            
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None
    
    def save_description_to_excel(self, reel_info):
        """Save reel description to Excel file"""
        try:
            df = pd.read_excel(self.description_file)
            new_row = {
                'URL': reel_info['url'],
                'Description': reel_info['description'],
                'Download_Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'Upload_Date': ''
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_excel(self.description_file, index=False)
        except Exception as e:
            logger.error(f"Failed to save description to Excel: {e}")
    
    def update_upload_date_in_excel(self, url):
        """Update upload date in Excel file"""
        try:
            df = pd.read_excel(self.description_file)
            df.loc[df['URL'] == url, 'Upload_Date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            df.to_excel(self.description_file, index=False)
        except Exception as e:
            logger.error(f"Failed to update upload date: {e}")
    
    def upload_reel(self, video_path, description, url):
        """Upload reel to Instagram"""
        try:
            self.client.clip_upload(video_path, description)
            self.update_upload_date_in_excel(url)
            logger.info(f"Successfully uploaded reel: {video_path}")
            
            # Delete the video file after upload
            if os.path.exists(video_path):
                os.remove(video_path)
                logger.info(f"Deleted video file: {video_path}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to upload {video_path}: {e}")
            return False
    
    def process_daily_reels(self):
        """Download and prepare 5 reels for the day"""
        available_reels = self.get_available_reels()
        
        if len(available_reels) < self.daily_limit:
            logger.warning(f"Not enough reels available. Found: {len(available_reels)}")
            return []
        
        # Select 5 random reels
        selected_reels = random.sample(available_reels, self.daily_limit)
        downloaded_reels = []
        
        for url in selected_reels:
            reel_data = self.download_reel(url)
            if reel_data:
                downloaded_reels.append(reel_data)
        
        # Mark reels as used
        used_reels = self.load_json_file(self.used_file)
        used_reels.extend(selected_reels)
        self.save_json_file(self.used_file, used_reels)
        
        # Store today's reels for upload
        today = datetime.now().strftime('%Y-%m-%d')
        daily_reels_file = f"daily_reels_{today}.json"
        self.save_json_file(daily_reels_file, downloaded_reels)
        
        logger.info(f"Prepared {len(downloaded_reels)} reels for today")
        return downloaded_reels
    
    def upload_next_reel(self):
        """Upload the next scheduled reel"""
        today = datetime.now().strftime('%Y-%m-%d')
        daily_reels_file = f"daily_reels_{today}.json"
        
        if not os.path.exists(daily_reels_file):
            logger.info("No reels prepared for today")
            return
        
        daily_reels = self.load_json_file(daily_reels_file)
        
        if not daily_reels:
            logger.info("All reels for today have been uploaded")
            return
        
        # Get the next reel to upload
        reel_data = daily_reels.pop(0)
        
        # Upload the reel
        success = self.upload_reel(
            reel_data['file_path'],
            reel_data['description'],
            reel_data['url']
        )
        
        if success:
            # Update the daily reels file
            self.save_json_file(daily_reels_file, daily_reels)
        else:
            # Put the reel back if upload failed
            daily_reels.insert(0, reel_data)
            self.save_json_file(daily_reels_file, daily_reels)
    
    def setup_schedule(self):
        """Setup the upload schedule"""
        # Weekday schedule (Monday to Friday)
        schedule.every().monday.at("07:30").do(self.upload_next_reel)
        schedule.every().monday.at("11:00").do(self.upload_next_reel)
        schedule.every().monday.at("13:30").do(self.upload_next_reel)
        schedule.every().monday.at("17:30").do(self.upload_next_reel)
        schedule.every().monday.at("21:00").do(self.upload_next_reel)
        
        schedule.every().tuesday.at("07:30").do(self.upload_next_reel)
        schedule.every().tuesday.at("11:00").do(self.upload_next_reel)
        schedule.every().tuesday.at("13:30").do(self.upload_next_reel)
        schedule.every().tuesday.at("17:30").do(self.upload_next_reel)
        schedule.every().tuesday.at("21:00").do(self.upload_next_reel)
        
        schedule.every().wednesday.at("07:30").do(self.upload_next_reel)
        schedule.every().wednesday.at("11:00").do(self.upload_next_reel)
        schedule.every().wednesday.at("13:30").do(self.upload_next_reel)
        schedule.every().wednesday.at("17:30").do(self.upload_next_reel)
        schedule.every().wednesday.at("21:00").do(self.upload_next_reel)
        
        schedule.every().thursday.at("07:30").do(self.upload_next_reel)
        schedule.every().thursday.at("11:00").do(self.upload_next_reel)
        schedule.every().thursday.at("13:30").do(self.upload_next_reel)
        schedule.every().thursday.at("17:30").do(self.upload_next_reel)
        schedule.every().thursday.at("21:00").do(self.upload_next_reel)
        
        schedule.every().friday.at("07:30").do(self.upload_next_reel)
        schedule.every().friday.at("11:00").do(self.upload_next_reel)
        schedule.every().friday.at("13:30").do(self.upload_next_reel)
        schedule.every().friday.at("17:30").do(self.upload_next_reel)
        schedule.every().friday.at("21:00").do(self.upload_next_reel)
        
        # Weekend schedule (Saturday & Sunday)
        schedule.every().saturday.at("09:00").do(self.upload_next_reel)
        schedule.every().saturday.at("12:00").do(self.upload_next_reel)
        schedule.every().saturday.at("15:00").do(self.upload_next_reel)
        schedule.every().saturday.at("18:30").do(self.upload_next_reel)
        schedule.every().saturday.at("21:30").do(self.upload_next_reel)
        
        schedule.every().sunday.at("09:00").do(self.upload_next_reel)
        schedule.every().sunday.at("12:00").do(self.upload_next_reel)
        schedule.every().sunday.at("15:00").do(self.upload_next_reel)
        schedule.every().sunday.at("18:30").do(self.upload_next_reel)
        schedule.every().sunday.at("21:30").do(self.upload_next_reel)
        
        # Daily preparation at midnight
        schedule.every().day.at("00:01").do(self.process_daily_reels)
        
        logger.info("Schedule setup complete")
    
    def run(self):
        """Main run loop"""
        logger.info("Starting Instagram Reel Bot")
        self.setup_schedule()
        
        # Process reels for today if not already done
        today = datetime.now().strftime('%Y-%m-%d')
        daily_reels_file = f"daily_reels_{today}.json"
        if not os.path.exists(daily_reels_file):
            self.process_daily_reels()
        
        # Keep the script running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

if __name__ == "__main__":
    bot = InstagramReelBot()
    bot.run()
