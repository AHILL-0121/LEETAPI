import requests
import json
import time
import os
import threading
import base64
import calendar as calendar_module
import datetime as dt_module
import pytz
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_file, Response
from flask_cors import CORS

# Configuration
LEETCODE_USERNAME = os.environ.get('LEETCODE_USERNAME', 'ahillselvaraaj')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'AHILL-0121/LEETAPI')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

headers = {
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

public_api_url = "https://leetcode.com/graphql"

recent_submissions_query = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug  
    timestamp
  }
}
"""

profile_query = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile {
      realName
      userAvatar
      ranking
      reputation
      starRanking
      aboutMe
      postViewCount
      postViewCountDiff
      school
      countryName
      company
      jobTitle
    }
    submitStats: submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
        submissions
      }
      totalSubmissionNum {
        difficulty
        count
        submissions
      }
    }
  }
}
"""

class LeetCodeAPI:
    def __init__(self):
        # Local file path only used for development environment
        self.submissions_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public', 'submissions.json')
        self.last_update = None
        self.update_interval = 3600  # 1 hour in seconds
        self.all_submissions = []
        self.external_apis = {
            "leetcode_stats_api": f"https://leetcode-stats-api.herokuapp.com/{LEETCODE_USERNAME}",
            "alfa_leetcode_api": f"https://alfa-leetcode-api.onrender.com/{LEETCODE_USERNAME}/"
        }
        
        # GitHub is the primary data storage, especially for serverless environments
        self.is_serverless = 'VERCEL' in os.environ
        if self.is_serverless:
            print("🚀 Running in serverless environment, using GitHub as primary storage")
        
        # Load submissions from GitHub
        self.load_all_submissions()
        
        # Start background update thread
        self.start_background_updates()

    def fetch_recent_submissions(self, limit=50):
        """Fetch recent accepted submissions using public API"""
        try:
            variables = {"username": LEETCODE_USERNAME, "limit": limit}
            response = requests.post(public_api_url, headers=headers, 
                                   json={"query": recent_submissions_query, "variables": variables})

            if response.status_code != 200:
                return []

            try:
                data = response.json()
            except Exception:
                return []

            if "errors" in data:
                return []

            submissions_data = data.get("data", {}).get("recentAcSubmissionList", [])

            if not submissions_data:
                return []

            recent_submissions = []
            for sub in submissions_data:
                # Make sure timestamp exists and is valid
                if "timestamp" not in sub or sub["timestamp"] is None:
                    print(f"⚠️ Skipping submission without timestamp: {sub.get('id', 'unknown')}")
                    continue
                    
                try:
                    submission_timestamp = int(sub["timestamp"])
                    
                    formatted_sub = {
                        "id": sub.get("id", ""),
                        "title": sub.get("title", ""),
                        "titleSlug": sub.get("titleSlug", ""),
                        "status": 10,
                        "language": "unknown",
                        "timestamp": str(submission_timestamp),  # Ensure it's a string
                        "submissionDate": format_timestamp_to_ist(submission_timestamp),
                        "runtime": "N/A",
                        "memory": "N/A",
                        "url": f"https://leetcode.com/problems/{sub.get('titleSlug', '')}/",
                        "isPending": False
                    }
                    recent_submissions.append(formatted_sub)
                except (ValueError, TypeError) as e:
                    print(f"⚠️ Error processing submission timestamp: {e} for sub {sub.get('id', 'unknown')}")

            return recent_submissions

        except Exception as e:
            return []

    def get_github_file_content(self, path):
        """Get file content from GitHub"""
        if not GITHUB_TOKEN:
            return None
            
        try:
            github_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}?ref={GITHUB_BRANCH}"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            response = requests.get(github_url, headers=headers)
            if response.status_code == 200:
                content = response.json()
                if content.get("encoding") == "base64" and content.get("content"):
                    return base64.b64decode(content["content"]).decode('utf-8')
            
            return None
        except Exception as e:
            print(f"❌ GitHub Error: {e}")
            return None

    def update_github_file(self, path, content, message):
        """Update file in GitHub repository"""
        if not GITHUB_TOKEN:
            print("⚠️ GitHub updates disabled - GITHUB_TOKEN not set")
            return False
            
        try:
            github_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            print(f"🔍 Getting SHA for: {path}")
            # Get current file to obtain the SHA
            try:
                response = requests.get(github_url, headers=headers, timeout=10)
                current_sha = None
                if response.status_code == 200:
                    current_sha = response.json().get("sha")
                    print(f"✅ Found SHA: {current_sha[:8]}...")
                else:
                    print(f"⚠️ File not found on GitHub (will create new): {response.status_code}")
            except Exception as sha_error:
                print(f"⚠️ Error getting SHA: {sha_error}")
            
            # Prepare update data
            update_data = {
                "message": message,
                "content": base64.b64encode(content.encode('utf-8')).decode('utf-8'),
                "branch": GITHUB_BRANCH
            }
            
            if current_sha:
                update_data["sha"] = current_sha
                print(f"🔄 Updating existing file on GitHub: {path}")
            else:
                print(f"➕ Creating new file on GitHub: {path}")
            
            # Update file
            try:
                print(f"📤 Sending update to GitHub...")
                response = requests.put(github_url, headers=headers, json=update_data, timeout=15)
                
                if response.status_code in [200, 201]:
                    print(f"✅ GitHub file updated: {path}")
                    return True
                else:
                    print(f"❌ GitHub update failed: {response.status_code}")
                    error_detail = response.text[:200] + "..." if len(response.text) > 200 else response.text
                    print(f"Error details: {error_detail}")
                    return False
            except Exception as put_error:
                print(f"❌ Error during GitHub PUT request: {put_error}")
                return False
                
        except Exception as e:
            print(f"❌ GitHub update error: {e}")
            return False

    def load_all_submissions(self):
        """Load all submissions from GitHub repository"""
        try:
            print("🔄 Loading submissions from GitHub repository...")
            github_content = self.get_github_file_content("public/submissions.json")
            
            if github_content:
                self.all_submissions = json.loads(github_content)
                print(f"✅ Loaded {len(self.all_submissions)} submissions from GitHub")
            else:
                print("⚠️ Submissions not found on GitHub, starting with empty list")
                self.all_submissions = []
                
            # Only save locally if in development environment (not on Vercel)
            if 'VERCEL' not in os.environ and github_content:
                try:
                    # Create directory if it doesn't exist
                    os.makedirs(os.path.dirname(self.submissions_file), exist_ok=True)
                    
                    # Save a local copy for development purposes only
                    with open(self.submissions_file, 'w', encoding='utf-8') as f:
                        json.dump(self.all_submissions, f, indent=2)
                    print("📝 Saved a local copy for development (not used in production)")
                except Exception as local_error:
                    print(f"⚠️ Could not save local copy: {local_error}")
        except Exception as e:
            print(f"❌ Error loading submissions from GitHub: {e}")
            self.all_submissions = []

    def save_all_submissions(self):
        """Save all submissions to GitHub repository"""
        try:
            # Prepare JSON content
            json_content = json.dumps(self.all_submissions, indent=2)
            
            # Update on GitHub (primary storage for serverless environment)
            now = get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"🔄 Auto-update submissions - {now}"
            print(f"� Saving {len(self.all_submissions)} submissions to GitHub repository...")
            github_result = self.update_github_file("public/submissions.json", json_content, message)
            
            # Only save locally if in development environment (not on Vercel)
            if 'VERCEL' not in os.environ:
                try:
                    directory = os.path.dirname(self.submissions_file)
                    if not os.path.exists(directory):
                        os.makedirs(directory, exist_ok=True)
                        
                    with open(self.submissions_file, 'w', encoding='utf-8') as f:
                        f.write(json_content)
                    print("📝 Saved a local copy for development (not used in production)")
                except Exception as local_error:
                    print(f"⚠️ Could not save local copy: {local_error}")
            
            # Return true only if GitHub update succeeded
            return github_result
        except Exception as e:
            print(f"❌ Error saving submissions to GitHub: {e}")
            return False

    def update_submissions_with_recent(self):
        """Update the submissions file with recent data from LeetCode"""
        try:
            print(f"🔄 Starting scheduled update at {get_ist_now()}")
            
            # Fetch recent submissions from the last 24 hours
            recent_submissions = self.fetch_recent_submissions(100)  # Fetch more to ensure we get all recent ones
            
            if not recent_submissions:
                print("ℹ️ No recent submissions found")
                return 0

            # Filter submissions from the last 24 hours
            cutoff_timestamp = int((get_ist_now() - timedelta(hours=24)).timestamp())
            recent_24h_submissions = []
            for sub in recent_submissions:
                try:
                    if "timestamp" in sub and sub["timestamp"] and int(sub["timestamp"]) >= cutoff_timestamp:
                        recent_24h_submissions.append(sub)
                except (ValueError, TypeError) as e:
                    print(f"⚠️ Error processing timestamp in recent filter: {e}")
                    
            print(f"📊 Found {len(recent_24h_submissions)} submissions from the last 24 hours")
            
            # If no submissions in the last 24 hours, return
            if not recent_24h_submissions:
                print("ℹ️ No submissions in the last 24 hours")
                return 0
                
            # Compare with existing submissions
            existing_ids = {sub["id"] for sub in self.all_submissions}
            
            # Find new submissions that don't exist in our database
            new_submissions = []
            for sub in recent_24h_submissions:
                if sub["id"] not in existing_ids:
                    new_submissions.append(sub)
                    
            if new_submissions:
                print(f"🔍 Found {len(new_submissions)} new submissions to add")
                
                # Add new submissions to the beginning and sort by timestamp (newest first)
                self.all_submissions = new_submissions + self.all_submissions
                
                # Safe sorting with error handling
                try:
                    self.all_submissions.sort(key=lambda x: int(x.get("timestamp", 0)), reverse=True)
                except (ValueError, TypeError) as e:
                    print(f"⚠️ Error sorting submissions: {e}, falling back to simpler sort")
                    # Fallback sorting method - no conversion to int
                    try:
                        self.all_submissions.sort(key=lambda x: x.get("timestamp", "0"), reverse=True)
                    except Exception as e2:
                        print(f"❌ Fallback sorting also failed: {e2}")
                
                # Save to file
                if self.save_all_submissions():
                    self.last_update = get_ist_now()
                    print(f"✅ Added {len(new_submissions)} new submissions")
                    return len(new_submissions)
            else:
                print("ℹ️ No new submissions found - database is up to date")
                # Still update the last_update timestamp
                self.last_update = get_ist_now()
                return 0

        except Exception as e:
            print(f"❌ Error updating submissions: {e}")
            return 0

    def background_update_worker(self):
        """Background worker for hourly updates"""
        while True:
            try:
                time.sleep(self.update_interval)
                self.update_submissions_with_recent()
            except Exception as e:
                print(f"❌ Background update error: {e}")
                time.sleep(60)  # Wait 1 minute before retrying

    def start_background_updates(self):
        """Start the background update thread"""
        try:
            update_thread = threading.Thread(target=self.background_update_worker, daemon=True)
            update_thread.start()
            print(f"⏰ Background updates started (every {self.update_interval//3600} hour)")
        except Exception as e:
            print(f"❌ Error starting background updates: {e}")

    def fetch_user_profile(self):
        """Fetch user profile data including avatar URL from multiple sources"""
        try:
            # First try official LeetCode GraphQL API
            profile_data = self._fetch_from_leetcode_graphql()
            
            # Then fetch from external APIs for enhanced data
            stats_data = self._fetch_from_external_apis()
            
            # Merge the data, with external APIs taking precedence for stats
            merged_profile = self._merge_profile_data(profile_data, stats_data)
            
            if merged_profile:
                return merged_profile
            elif stats_data:
                # If only external data is available, return that
                return stats_data
            else:
                # Last-resort fallback – count unique problem slugs in the local DB
                local_total = len(set(
                    sub.get("titleSlug") or sub.get("title", "")
                    for sub in self.all_submissions
                ))
                return {
                    "username": LEETCODE_USERNAME,
                    "avatar": "https://assets.leetcode.com/users/ahillselvaraaj/avatar_1749400789.png",
                    "submissions": {"easy": 0, "medium": 0, "hard": 0, "total": local_total},
                    "ranking": 0,
                    "data_source": "local_db_fallback"
                }
            
        except Exception as e:
            print(f"❌ Error fetching user profile: {e}")
            return None
            
    def _fetch_from_leetcode_graphql(self):
        """Fetch profile data from LeetCode GraphQL API"""
        try:
            variables = {"username": LEETCODE_USERNAME}
            response = requests.post(public_api_url, headers=headers, 
                                  json={"query": profile_query, "variables": variables})

            if response.status_code != 200:
                print(f"⚠️ LeetCode GraphQL API returned status {response.status_code}")
                return None

            try:
                data = response.json()
            except Exception as e:
                print(f"⚠️ Error parsing JSON from LeetCode GraphQL API: {e}")
                return None

            if "errors" in data:
                print(f"⚠️ LeetCode GraphQL API returned errors")
                return None

            user_data = data.get("data", {}).get("matchedUser", {})
            if not user_data:
                print(f"⚠️ No user data found in LeetCode GraphQL API response")
                return None
                
            # Extract profile data
            profile = user_data.get("profile", {})
            submit_stats = user_data.get("submitStats", {})
            
            # Get submission counts by difficulty
            ac_submissions = {}
            for item in submit_stats.get("acSubmissionNum", []):
                ac_submissions[item.get("difficulty", "").lower()] = {
                    "count": item.get("count", 0),
                    "submissions": item.get("submissions", 0)
                }
                
            # Format the profile data
            formatted_profile = {
                "username": user_data.get("username", ""),
                "realName": profile.get("realName", ""),
                "avatar": profile.get("userAvatar", ""),
                "ranking": profile.get("ranking", 0),
                "reputation": profile.get("reputation", 0),
                "countryName": profile.get("countryName", ""),
                "company": profile.get("company", ""),
                "school": profile.get("school", ""),
                "jobTitle": profile.get("jobTitle", ""),
                "submissions": {
                    "easy": ac_submissions.get("easy", {}).get("count", 0),
                    "medium": ac_submissions.get("medium", {}).get("count", 0),
                    "hard": ac_submissions.get("hard", {}).get("count", 0),
                    "total": sum(item.get("count", 0) for item in submit_stats.get("acSubmissionNum", []))
                },
                "data_source": "leetcode_graphql"
            }
            
            return formatted_profile
            
        except Exception as e:
            print(f"❌ Error fetching from LeetCode GraphQL API: {e}")
            return None
            
    def _fetch_from_external_apis(self):
        """Fetch profile data from external LeetCode stats APIs"""
        try:
            combined_data = {
                "username": LEETCODE_USERNAME,
                "external_sources": [],
                "data_source": "external_apis"
            }
            
            # Try LeetCode Stats API (Heroku)
            try:
                response = requests.get(self.external_apis["leetcode_stats_api"], timeout=5)
                if response.status_code == 200:
                    stats_data = response.json()
                    if stats_data:
                        combined_data["external_sources"].append("leetcode_stats_api")
                        combined_data["status"] = stats_data.get("status")
                        combined_data["message"] = stats_data.get("message")
                        combined_data["total_solving_count"] = stats_data.get("totalSolved")
                        combined_data["acceptance_rate"] = stats_data.get("acceptanceRate")
                        combined_data["easy_solved"] = stats_data.get("easySolved")
                        combined_data["total_easy"] = stats_data.get("totalEasy")
                        combined_data["medium_solved"] = stats_data.get("mediumSolved")
                        combined_data["total_medium"] = stats_data.get("totalMedium")
                        combined_data["hard_solved"] = stats_data.get("hardSolved")
                        combined_data["total_hard"] = stats_data.get("totalHard")
                        combined_data["ranking"] = stats_data.get("ranking")
                        combined_data["contribution_points"] = stats_data.get("contributionPoints")
                        combined_data["reputation"] = stats_data.get("reputation")
                        
                        # Set the submission counts
                        combined_data["submissions"] = {
                            "easy": stats_data.get("easySolved", 0),
                            "medium": stats_data.get("mediumSolved", 0),
                            "hard": stats_data.get("hardSolved", 0),
                            "total": stats_data.get("totalSolved", 0)
                        }
            except Exception as e:
                print(f"⚠️ Error fetching from LeetCode Stats API: {e}")
                
            # Try Alfa LeetCode API (Render)
            try:
                response = requests.get(self.external_apis["alfa_leetcode_api"], timeout=5)
                if response.status_code == 200:
                    alfa_data = response.json()
                    if alfa_data:
                        combined_data["external_sources"].append("alfa_leetcode_api")
                        # Extract useful fields from this API
                        if "avatar" not in combined_data or not combined_data["avatar"]:
                            combined_data["avatar"] = alfa_data.get("avatar_url", "")
                        
                        combined_data["alfa_status"] = alfa_data.get("status")
                        combined_data["streak"] = alfa_data.get("streak")
                        combined_data["active_days"] = alfa_data.get("active_days")
                        combined_data["max_streak"] = alfa_data.get("max_streak")
                        
                        # Override submissions if available and not already set
                        if "total_problems_solved" in alfa_data:
                            if "submissions" not in combined_data:
                                combined_data["submissions"] = {}
                                
                            combined_data["submissions"]["total"] = alfa_data.get("total_problems_solved", 0)
                        
                        # Add any additional useful fields
                        if "real_name" in alfa_data and alfa_data["real_name"]:
                            combined_data["realName"] = alfa_data["real_name"]
                        
                        if "country_name" in alfa_data and alfa_data["country_name"]:
                            combined_data["countryName"] = alfa_data["country_name"]
            except Exception as e:
                print(f"⚠️ Error fetching from Alfa LeetCode API: {e}")
                
            # Return None if no external data was retrieved
            if len(combined_data["external_sources"]) == 0:
                print("⚠️ No data retrieved from external APIs")
                return None
                
            return combined_data
            
        except Exception as e:
            print(f"❌ Error fetching from external APIs: {e}")
            return None
            
    def check_api_status(self):
        """Check the status of all external APIs"""
        status = {
            "leetcode_graphql": False,
            "external_apis": {}
        }
        
        # Check LeetCode GraphQL API
        try:
            variables = {"username": LEETCODE_USERNAME}
            response = requests.post(public_api_url, headers=headers, 
                                    json={"query": profile_query, "variables": variables}, 
                                    timeout=5)
            status["leetcode_graphql"] = response.status_code == 200
        except Exception:
            pass
            
        # Check external APIs
        for name, url in self.external_apis.items():
            try:
                response = requests.get(url, timeout=5)
                status["external_apis"][name] = {
                    "status": response.status_code == 200,
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000)
                }
            except Exception as e:
                status["external_apis"][name] = {
                    "status": False,
                    "error": str(e)
                }
                
        return status
            
    def _merge_profile_data(self, primary_data, secondary_data):
        """Merge profile data from different sources, with secondary taking precedence for stats"""
        if not primary_data and not secondary_data:
            return None
            
        if not primary_data:
            return secondary_data
            
        if not secondary_data:
            return primary_data
            
        # Start with the primary data
        merged = dict(primary_data)
        
        # Add data source information
        merged["data_sources"] = []
        if primary_data.get("data_source"):
            merged["data_sources"].append(primary_data["data_source"])
        if secondary_data.get("data_source"):
            merged["data_sources"].append(secondary_data["data_source"])
        if secondary_data.get("external_sources"):
            merged["external_sources"] = secondary_data["external_sources"]
            
        # Use avatar from secondary if available
        if secondary_data.get("avatar") and not merged.get("avatar"):
            merged["avatar"] = secondary_data["avatar"]
            
        # Override submission stats from secondary only when it has real (non-zero) data.
        # A falsy-looking dict like {"easy":0,"medium":0,"hard":0,"total":0} is truthy in
        # Python, so we guard explicitly on total > 0 to avoid wiping correct GraphQL stats.
        sec_subs = secondary_data.get("submissions") or {}
        if sec_subs.get("total", 0) > 0:
            merged["submissions"] = sec_subs
            
        # Add additional stats from secondary
        for key in ["streak", "active_days", "max_streak", "acceptance_rate", 
                    "contribution_points", "total_easy", "total_medium", "total_hard"]:
            if key in secondary_data:
                merged[key] = secondary_data[key]
                
        # Use ranking from secondary if available
        if secondary_data.get("ranking"):
            merged["ranking"] = secondary_data["ranking"]
            
        return merged

    def get_all_submissions(self, limit=None):
        """Get all submissions with optional limit"""
        if limit:
            return self.all_submissions[:limit]
        return self.all_submissions

# ─────────────────────────────────────────────────────────────────────────────
# Heatmap helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_day_counts(submissions, year):
    """Return {date_str: count} for every accepted submission in *year*."""
    counts = {}
    for sub in submissions:
        try:
            date_part = sub.get('submissionDate', '')
            if date_part and date_part[:4] == str(year):
                d = date_part[:10]          # "YYYY-MM-DD"
                counts[d] = counts.get(d, 0) + 1
            else:
                ts = int(sub.get('timestamp', 0))
                if ts == 0:
                    continue
                d = datetime.fromtimestamp(ts, pytz.UTC).astimezone(
                    pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d')
                if d[:4] == str(year):
                    counts[d] = counts.get(d, 0) + 1
        except Exception:
            pass
    return counts


def calculate_streak(counts, year):
    """Return (current_streak, longest_streak) in days for *year*."""
    today = datetime.now(pytz.UTC).astimezone(pytz.timezone('Asia/Kolkata')).date()
    start = dt_module.date(year, 1, 1)
    end   = min(dt_module.date(year, 12, 31), today)

    longest = cur_temp = 0
    day = start
    while day <= end:
        if counts.get(day.strftime('%Y-%m-%d'), 0) > 0:
            cur_temp += 1
            longest = max(longest, cur_temp)
        else:
            cur_temp = 0
        day += dt_module.timedelta(days=1)

    # Walk backwards from today for the *current* streak
    current = 0
    check = today
    while check >= start:
        if counts.get(check.strftime('%Y-%m-%d'), 0) > 0:
            current += 1
            check -= dt_module.timedelta(days=1)
        else:
            break

    return current, longest


def generate_heatmap_svg(username, year, counts, total_submissions, streak, longest_streak):
    """Generate a beautiful animated GitHub-style submission heatmap SVG."""

    # ── Palette ───────────────────────────────────────────────────────────
    BG_COLOR     = '#ffffff'
    BORDER_COLOR = '#d0d7de'
    EMPTY_COLOR  = '#ebedf0'
    TEXT_COLOR   = '#57606a'
    TITLE_COLOR  = '#1f2328'
    ACCENT_COLOR = '#1a7f37'
    COLOR_SCALE  = [
        {'min': 1, 'max': 1,             'color': '#9be9a8'},
        {'min': 2, 'max': 3,             'color': '#40c463'},
        {'min': 4, 'max': 6,             'color': '#30a14e'},
        {'min': 7, 'max': float('inf'), 'color': '#216e39'},
    ]

    def get_color(count):
        if count == 0:
            return EMPTY_COLOR
        for e in COLOR_SCALE:
            if e['min'] <= count <= e['max']:
                return e['color']
        return COLOR_SCALE[-1]['color']

    # ── Layout ────────────────────────────────────────────────────────────
    CELL = 11
    GAP  = 2
    STEP = CELL + GAP
    PAD_L, PAD_T, PAD_R, PAD_B = 38, 30, 22, 8
    MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun',
                   'Jul','Aug','Sep','Oct','Nov','Dec']

    def ry(row): return PAD_T + row * STEP
    def cx(col): return PAD_L + col * STEP

    # ── Build grid (each month starts fresh) ─────────────────────────────
    cells = []
    month_start_cols = []
    global_col = 0

    for month in range(12):
        month_start_cols.append(global_col)
        first_day  = dt_module.date(year, month + 1, 1)
        first_dow  = (first_day.weekday() + 1) % 7   # Sunday = 0
        total_days = calendar_module.monthrange(year, month + 1)[1]
        col, row = global_col, first_dow

        for day in range(1, total_days + 1):
            ds = f"{year}-{str(month+1).zfill(2)}-{str(day).zfill(2)}"
            cnt = counts.get(ds, 0)
            cells.append({'x': cx(col), 'y': ry(row),
                          'color': get_color(cnt), 'count': cnt, 'date': ds})
            row += 1
            if row == 7:
                row = 0
                col += 1

        global_col = col + 1

    total_columns = global_col
    SVG_W   = PAD_L + total_columns * STEP + PAD_R
    SVG_H   = PAD_T + 7 * STEP + PAD_B
    TOTAL_H = SVG_H + 30 + 36   # +legend +stats

    # ── CSS ───────────────────────────────────────────────────────────────
    css = """<defs>
      <filter id="glow">
        <feGaussianBlur stdDeviation="2" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
      <linearGradient id="bgGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color="#ffffff"/>
        <stop offset="100%" stop-color="#f6f8fa"/>
      </linearGradient>
    </defs>
    <style>
      @keyframes cellIn {
        0%   { opacity:0; transform:scale(0.2); }
        60%  { opacity:1; transform:scale(1.15); }
        100% { opacity:1; transform:scale(1); }
      }
      @keyframes slideUp {
        from { opacity:0; transform:translateY(8px); }
        to   { opacity:1; transform:translateY(0); }
      }
      @keyframes legendFade {
        from { opacity:0; }
        to   { opacity:1; }
      }
      .cell { opacity:0; animation:cellIn 0.3s ease forwards; }
      .cell:hover { filter:url(#glow) brightness(1.6); cursor:pointer; }
      .stat { animation:slideUp 0.45s ease both; }
      .legend-item { animation:legendFade 0.4s ease 0.7s both; }
    </style>"""

    # ── Cells ─────────────────────────────────────────────────────────────
    rects = []
    for i, c in enumerate(cells):
        delay = (i * 2) % 700
        tip   = f"{c['date']}: {c['count']} submission{'s' if c['count']!=1 else ''}"
        rects.append(
            f'<rect class="cell" x="{c["x"]}" y="{c["y"]}" '
            f'width="{CELL}" height="{CELL}" rx="2" ry="2" fill="{c["color"]}" '
            f'style="animation-delay:{delay}ms">'
            f'<title>{tip}</title></rect>'
        )

    # ── Month labels ──────────────────────────────────────────────────────
    mlabel_y = ry(7) + 13
    month_labels = [
        f'<text x="{cx(col)}" y="{mlabel_y}" font-size="10" fill="{TEXT_COLOR}" '
        f'text-anchor="start" font-family="system-ui,-apple-system,sans-serif">'
        f'{MONTH_NAMES[i]}</text>'
        for i, col in enumerate(month_start_cols)
    ]

    # ── Day labels (Mon / Wed / Fri) ──────────────────────────────────────
    day_labels = [
        f'<text x="{PAD_L - 5}" y="{ry(row) + CELL - 1}" font-size="9" '
        f'fill="{TEXT_COLOR}" text-anchor="end" '
        f'font-family="system-ui,-apple-system,sans-serif">{lbl}</text>'
        for row, lbl in [(1,'Mon'),(3,'Wed'),(5,'Fri')]
    ]

    # ── Legend ────────────────────────────────────────────────────────────
    leg_y  = SVG_H + 9
    leg_x0 = SVG_W - 195
    leg_colors = [EMPTY_COLOR] + [s['color'] for s in COLOR_SCALE]
    legend_parts = [
        f'<text class="legend-item" x="{leg_x0}" y="{leg_y+CELL-1}" '
        f'font-size="9" fill="{TEXT_COLOR}" '
        f'font-family="system-ui,-apple-system,sans-serif">Less</text>'
    ]
    lcx = leg_x0 + 34
    for color in leg_colors:
        legend_parts.append(
            f'<rect class="legend-item" x="{lcx}" y="{leg_y}" '
            f'width="{CELL}" height="{CELL}" rx="2" ry="2" fill="{color}"/>'
        )
        lcx += STEP
    legend_parts.append(
        f'<text class="legend-item" x="{lcx+2}" y="{leg_y+CELL-1}" '
        f'font-size="9" fill="{TEXT_COLOR}" '
        f'font-family="system-ui,-apple-system,sans-serif">More</text>'
    )

    # ── Stats bar ─────────────────────────────────────────────────────────
    sy  = SVG_H + 30 + 22
    mid = SVG_W / 2

    def ex(s):
        return (str(s).replace('&','&amp;').replace('<','&lt;')
                      .replace('>','&gt;').replace('"','&quot;').replace("'",'&apos;'))

    sub_word = 'submission' if total_submissions == 1 else 'submissions'
    dl = f'animation-delay:0.5s'
    stats_parts = [
        f'<text class="stat" x="{PAD_L}" y="{sy}" font-size="11.5" '
        f'fill="{TITLE_COLOR}" font-weight="700" '
        f'font-family="system-ui,-apple-system,sans-serif" style="{dl}">'
        f'{ex(username)}</text>',

        f'<text class="stat" x="{mid}" y="{sy}" font-size="11" '
        f'fill="{TEXT_COLOR}" text-anchor="middle" '
        f'font-family="system-ui,-apple-system,sans-serif" style="{dl}">'
        f'{total_submissions} {sub_word} in {year}</text>',

        f'<text class="stat" x="{mid + 110}" y="{sy}" font-size="11" '
        f'fill="{ACCENT_COLOR}" text-anchor="middle" '
        f'font-family="system-ui,-apple-system,sans-serif" style="{dl}">'
        f'&#x1F525; Streak: {streak}d</text>',

        f'<text class="stat" x="{SVG_W - PAD_R}" y="{sy}" font-size="11" '
        f'fill="{TEXT_COLOR}" text-anchor="end" '
        f'font-family="system-ui,-apple-system,sans-serif" style="{dl}">'
        f'Best: {longest_streak}d</text>',
    ]

    # ── Assemble ──────────────────────────────────────────────────────────
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{SVG_W}" height="{TOTAL_H}" '
        f'viewBox="0 0 {SVG_W} {TOTAL_H}" role="img">\n'
        + css + '\n'
        + f'<rect width="{SVG_W}" height="{TOTAL_H}" rx="10" ry="10" '
          f'fill="url(#bgGrad)" stroke="{BORDER_COLOR}" stroke-width="1"/>\n'
        + '\n'.join(month_labels) + '\n'
        + '\n'.join(day_labels) + '\n'
        + '\n'.join(rects) + '\n'
        + '\n'.join(legend_parts) + '\n'
        + '\n'.join(stats_parts) + '\n'
        + '</svg>'
    )


# Initialize API
leetcode_api = LeetCodeAPI()

# Create Flask app
app = Flask(__name__)
# Enable CORS for all routes and origins
CORS(app, resources={r"/*": {"origins": "*"}})

# Add CORS headers to all responses
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

# IST timezone configuration
IST = pytz.timezone('Asia/Kolkata')

def get_ist_now():
    """Return current datetime in IST timezone"""
    return datetime.now(pytz.UTC).astimezone(IST)

def format_timestamp_to_ist(timestamp):
    """Convert a unix timestamp to IST formatted string"""
    dt = datetime.fromtimestamp(int(timestamp), pytz.UTC).astimezone(IST)
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def get_ist_timestamp():
    """Get current timestamp in IST timezone"""
    return int(get_ist_now().timestamp())

# API Routes
@app.route('/api/submissions', methods=['GET'])
def get_submissions():
    """Get submissions - always fetch fresh from LeetCode"""
    try:
        limit = request.args.get('limit', 50, type=int)
        submissions = leetcode_api.fetch_recent_submissions(limit)
        
        return jsonify({
            "success": True,
            "count": len(submissions),
            "platform": "vercel",
            "data": submissions
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/submissions/recent', methods=['GET'])
def get_recent_submissions():
    """Get recent submissions from last N hours"""
    try:
        hours = request.args.get('hours', 12, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        # Fetch fresh data
        all_submissions = leetcode_api.fetch_recent_submissions(limit)
        cutoff_timestamp = int((get_ist_now() - timedelta(hours=hours)).timestamp())
        
        # Filter by time with error handling
        recent_submissions = []
        for sub in all_submissions:
            try:
                if "timestamp" in sub and sub["timestamp"] and int(sub["timestamp"]) >= cutoff_timestamp:
                    recent_submissions.append(sub)
            except (ValueError, TypeError) as e:
                print(f"⚠️ Error processing timestamp in recent submissions filter: {e}")
        
        return jsonify({
            "success": True,
            "count": len(recent_submissions),
            "hours_back": hours,
            "data": recent_submissions
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/submissions/fetch-recent', methods=['POST'])
def fetch_recent_from_leetcode():
    """Fetch fresh submissions from LeetCode public API"""
    try:
        limit = 50
        if request.is_json and request.json:
            limit = request.json.get('limit', 50)
        
        fresh_submissions = leetcode_api.fetch_recent_submissions(limit)
        
        return jsonify({
            "success": True,
            "message": f"Fetched {len(fresh_submissions)} recent submissions from LeetCode",
            "count": len(fresh_submissions),
            "data": fresh_submissions
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get API status and information"""
    # Quick fetch to get current count
    submissions = leetcode_api.fetch_recent_submissions(10)
    
    github_status = {
        "enabled": bool(GITHUB_TOKEN),
        "repository": GITHUB_REPO,
        "branch": GITHUB_BRANCH
    }
    
    # Include persistence warning if GitHub integration is not enabled
    persistence_info = []
    if not GITHUB_TOKEN:
        persistence_info = [
            "⚠️ GitHub integration NOT enabled - updates will not persist",
            "Set GITHUB_TOKEN in Vercel environment variables for persistent storage",
            "See /api/github/status for setup instructions"
        ]
        
    # Get user profile info
    user_profile = leetcode_api.fetch_user_profile()
    
    return jsonify({
        "success": True,
        "status": "running",
        "platform": "vercel_serverless",
        "username": LEETCODE_USERNAME,
        "profile": user_profile,
        "sample_submissions": len(submissions),
        "database": {
            "storage_type": "github_repository",
            "total_submissions": len(leetcode_api.all_submissions),
            "last_update": leetcode_api.last_update.isoformat() if leetcode_api.last_update else None,
            "auto_update_interval": f"{leetcode_api.update_interval//3600} hour(s)"
        },
        "persistence": github_status,
        "features": [
            "Serverless architecture",
            "No authentication required", 
            "Fresh data on every request",
            "Automatic hourly updates",
            "GitHub as primary data storage",
            "No dependency on local file system",
            "User profile with enhanced data from multiple sources"
        ],
        "persistence_warnings": persistence_info,
        "endpoints": {
            "GET /api/profile": "Get user profile with avatar and submission stats",
            "GET /api/submissions": "Get fresh submissions from LeetCode API",
            "GET /api/submissions/all": "Get all submissions from local database",
            "GET /api/submissions/recent": "Get recent submissions by time filter",
            "POST /api/submissions/fetch-recent": "Fetch fresh submissions with custom limit",
            "POST /api/submissions/update": "Manually update local database",
            "GET /api/refresh": "Simple refresh endpoint",
            "GET /api/github/status": "Check GitHub integration status",
            "GET /api/status": "Get API status and info",
            "GET /health": "Health check"
        }
    })

@app.route('/api/submissions/all', methods=['GET'])
def get_all_submissions():
    """Get all submissions from local database"""
    try:
        limit = request.args.get('limit', type=int)
        all_submissions = leetcode_api.get_all_submissions(limit)
        
        return jsonify({
            "success": True,
            "count": len(all_submissions),
            "total_submissions": len(leetcode_api.all_submissions),
            "platform": "vercel",
            "source": "local_database",
            "last_update": leetcode_api.last_update.isoformat() if leetcode_api.last_update else None,
            "data": all_submissions
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/submissions/update', methods=['POST', 'GET'])
def manual_update_submissions():
    """Manually trigger submissions database update"""
    try:
        print(f"🔄 Manual update triggered at {get_ist_now()}")
        old_count = len(leetcode_api.all_submissions)
        
        # Get timestamp of last update
        last_update_time = leetcode_api.last_update
        
        # Update with recent submissions (checks last 24 hours)
        new_submissions_count = leetcode_api.update_submissions_with_recent()
        
        github_status = "enabled" if GITHUB_TOKEN else "disabled (no token)"
        
        return jsonify({
            "success": True,
            "message": f"Manual update completed - {new_submissions_count} new submissions added" if new_submissions_count > 0 else "No new submissions found",
            "new_submissions_added": new_submissions_count,
            "total_submissions": len(leetcode_api.all_submissions),
            "last_update": leetcode_api.last_update.isoformat() if leetcode_api.last_update else None,
            "previous_update": last_update_time.isoformat() if last_update_time else None,
            "next_auto_update": f"Every {leetcode_api.update_interval//3600} hour(s)",
            "github_sync": github_status,
            "update_strategy": "Checks last 24 hours of submissions and adds any new ones",
            "environment": "vercel_serverless"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/refresh', methods=['GET', 'POST'])
def refresh_submissions():
    """Simple refresh endpoint - alias for update"""
    try:
        print(f"🔄 Refresh triggered at {get_ist_now()}")
        
        new_submissions_count = leetcode_api.update_submissions_with_recent()
        
        github_status = "enabled" if GITHUB_TOKEN else "disabled (no token)"
        
        return jsonify({
            "success": True,
            "action": "refresh_completed",
            "message": f"Found {new_submissions_count} new submissions" if new_submissions_count > 0 else "No new submissions to add",
            "new_submissions_added": new_submissions_count,
            "total_submissions": len(leetcode_api.all_submissions),
            "timestamp": get_ist_now().isoformat(),
            "github_sync": github_status,
            "note": "If GitHub sync is disabled, you need to set GITHUB_TOKEN in Vercel environment variables"
        })
    except Exception as e:
        print(f"❌ Error in refresh endpoint: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/submissions/download', methods=['GET'])
def download_submissions():
    """Download all submissions as JSON file"""
    try:
        return send_file(
            leetcode_api.submissions_file,
            as_attachment=True,
            download_name='leetcode_submissions.json',
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Could not download file: {str(e)}"
        }), 500

@app.route('/', methods=['GET'])
def home():
    """Home page with API documentation"""
    # Check if request accepts HTML (browser request)
    if 'text/html' in request.headers.get('Accept', ''):
        # Get profile information including avatar
        user_profile = leetcode_api.fetch_user_profile() or {
            "username": LEETCODE_USERNAME,
            "avatar": "https://assets.leetcode.com/users/ahillselvaraaj/avatar_1749400789.png",
            "submissions": {"easy": 0, "medium": 0, "hard": 0, "total": 0},
            "ranking": 0
        }

        avatar_url = user_profile.get("avatar") or "https://assets.leetcode.com/users/ahillselvaraaj/avatar_1749400789.png"
        username   = user_profile.get("username", LEETCODE_USERNAME)
        ranking    = user_profile.get("ranking", "N/A")

        # Get submission stats
        submissions = user_profile.get("submissions", {})
        easy   = submissions.get("easy",   0)
        medium = submissions.get("medium", 0)
        hard   = submissions.get("hard",   0)
        total  = submissions.get("total",  0)

        # Heatmap for current year
        cur_year = get_ist_now().year
        heatmap_counts        = build_day_counts(leetcode_api.all_submissions, cur_year)
        heatmap_total         = sum(heatmap_counts.values())
        heatmap_streak, heatmap_longest = calculate_streak(heatmap_counts, cur_year)
        heatmap_svg = generate_heatmap_svg(
            username, cur_year, heatmap_counts,
            heatmap_total, heatmap_streak, heatmap_longest
        )
        # Inline as data URI so no extra HTTP round-trip
        import base64 as _b64
        heatmap_b64  = _b64.b64encode(heatmap_svg.encode()).decode()
        heatmap_data = f"data:image/svg+xml;base64,{heatmap_b64}"

        db_total = len(leetcode_api.all_submissions)
        warn_block = '' if GITHUB_TOKEN else (
            '<div class="warn-box">'
            '<strong>⚠️ GitHub token not set.</strong><br>'
            'Updates will not persist. Set GITHUB_TOKEN in Vercel env vars.'
            '</div>'
        )

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LeetCode Submissions API</title>
  <link rel="icon" href="/favicon.ico" type="image/x-icon">
  <style>
    :root {{
      --bg:       #f6f8fa;
      --surface:  #ffffff;
      --surface2: #f0f3f6;
      --border:   #d0d7de;
      --text:     #1f2328;
      --muted:    #57606a;
      --easy:     #1a7f37;
      --medium:   #9a6700;
      --hard:     #cf222e;
      --accent:   #0969da;
      --green:    #1a7f37;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg); color: var(--text);
      max-width: 900px; margin: 0 auto; padding: 2rem 1.5rem;
      line-height: 1.6;
    }}

    /* ── Animations ──────────────────────────────────── */
    @keyframes fadeDown {{
      from {{ opacity: 0; transform: translateY(-14px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(14px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes popIn {{
      0%   {{ opacity: 0; transform: scale(0.85); }}
      70%  {{ opacity: 1; transform: scale(1.04); }}
      100% {{ transform: scale(1); }}
    }}
    @keyframes countUp {{
      from {{ opacity: 0; transform: scale(0.6); }}
      to   {{ opacity: 1; transform: scale(1); }}
    }}
    @keyframes shimmer {{
      0%   {{ background-position: -400px 0; }}
      100% {{ background-position:  400px 0; }}
    }}

    .fade-down {{ animation: fadeDown 0.5s ease both; }}
    .fade-up   {{ animation: fadeUp  0.5s ease both; }}

    /* ── Header ──────────────────────────────────────── */
    .header {{
      text-align: center; margin-bottom: 2rem;
      animation: fadeDown 0.5s ease both;
    }}
    .header h1 {{
      font-size: 1.9rem; font-weight: 700;
      background: linear-gradient(90deg, #0969da, #1a7f37);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .header p {{ color: var(--muted); margin-top: .4rem; }}
    .badge {{
      display: inline-block; background: var(--surface2);
      border: 1px solid var(--border);
      color: var(--muted); padding: 0.15rem 0.55rem;
      border-radius: 999px; font-size: 0.75rem;
    }}

    /* ── Profile card ────────────────────────────────── */
    .profile-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px; padding: 1.75rem;
      display: flex; flex-direction: column; align-items: center;
      text-align: center;
      animation: popIn 0.55s ease 0.1s both;
      box-shadow: 0 2px 12px rgba(0,0,0,.08);
    }}
    .avatar-wrap {{
      position: relative; margin-bottom: 1rem;
    }}
    .profile-avatar {{
      width: 92px; height: 92px; border-radius: 50%;
      border: 3px solid var(--green); object-fit: cover;
      display: block;
      box-shadow: 0 0 14px rgba(26,127,55,.25);
    }}
    .online-dot {{
      position: absolute; bottom: 4px; right: 4px;
      width: 14px; height: 14px; border-radius: 50%;
      background: var(--green); border: 2px solid var(--surface);
    }}
    .profile-name {{ font-size: 1.4rem; font-weight: 700; color: var(--text); }}
    .profile-rank {{ color: var(--muted); font-size: 0.9rem; margin: .25rem 0 1rem; }}

    .stats-grid {{
      display: flex; gap: 1px; width: 100%; max-width: 420px;
      background: var(--border); border-radius: 10px; overflow: hidden;
      margin-top: 0.5rem;
    }}
    .stat-box {{
      flex: 1; background: var(--surface2); padding: .75rem .5rem;
      text-align: center; transition: background .2s;
    }}
    .stat-box:hover {{ background: #e8ecf0; }}
    .stat-value {{
      font-size: 1.5rem; font-weight: 700;
      animation: countUp 0.6s ease both;
    }}
    .stat-label {{ font-size: 0.7rem; text-transform: uppercase; color: var(--muted); letter-spacing: .04em; }}
    .easy   {{ color: var(--easy);   }}
    .medium {{ color: var(--medium); }}
    .hard   {{ color: var(--hard);   }}
    .total  {{ color: var(--accent); }}

    /* ── Heatmap section ─────────────────────────────── */
    .heatmap-section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px; padding: 1.25rem 1.5rem;
      margin: 1.5rem 0;
      animation: fadeUp 0.55s ease 0.2s both;
      box-shadow: 0 2px 12px rgba(0,0,0,.06);
    }}
    .heatmap-section h3 {{
      color: var(--text); font-size: 1rem; margin-bottom: 1rem;
      display: flex; align-items: center; gap: .5rem;
    }}
    .heatmap-img {{
      width: 100%; border-radius: 8px;
      display: block;
    }}

    /* ── Endpoints ───────────────────────────────────── */
    .endpoints-title {{
      font-size: 1rem; font-weight: 600; color: var(--text);
      margin: 1.5rem 0 0.75rem;
      animation: fadeUp 0.45s ease 0.3s both;
    }}
    .endpoint {{
      background: var(--surface); border: 1px solid var(--border);
      padding: .85rem 1rem; margin: .5rem 0;
      border-radius: 10px; transition: border-color .2s, transform .15s, box-shadow .2s;
      animation: fadeUp 0.4s ease both;
    }}
    .endpoint:hover {{
      border-color: var(--accent);
      transform: translateX(3px);
      box-shadow: 0 2px 10px rgba(9,105,218,.12);
    }}
    .endpoint p {{ color: var(--muted); font-size: 0.88rem; margin-top: .3rem; }}
    .method {{
      display: inline-block; padding: .18rem .55rem;
      border-radius: 5px; font-weight: 700; font-size: .78rem;
      margin-right: .4rem;
    }}
    .get  {{ background: #dafbe1; color: #116329; border: 1px solid #84e4a5; }}
    .post {{ background: #ddf4ff; color: #0550ae; border: 1px solid #80ccff; }}
    code {{
      background: var(--surface2); border: 1px solid var(--border);
      padding: .1rem .4rem; border-radius: 4px; font-size: .875em;
      color: #cf222e;
    }}
    small code {{ font-size: .8em; }}

    /* ── Warn / footer ───────────────────────────────── */
    .warn-box {{
      background: #fff8c5; border: 1px solid #d4a72c; color: #7d4e00;
      padding: .9rem 1rem; border-radius: 8px; margin-top: 1.5rem;
      font-size: .875rem;
    }}
    .footer {{
      text-align: center; margin-top: 2rem; color: var(--muted);
      font-size: .85rem; animation: fadeUp 0.5s ease 0.5s both;
    }}
  </style>
</head>
<body>

  <div class="header">
    <h1>🚀 LeetCode Submissions API</h1>
    <p>Serverless API for LeetCode submissions &nbsp;•&nbsp; <span class="badge">v3.0.0</span></p>
  </div>

  <!-- Profile card -->
  <div class="profile-card">
    <div class="avatar-wrap">
      <img src="{avatar_url}" alt="Profile" class="profile-avatar"
           onerror="this.src='https://assets.leetcode.com/users/default_avatar.jpg'">
      <span class="online-dot"></span>
    </div>
    <div class="profile-name">{username}</div>
    <div class="profile-rank">Rank: {ranking}</div>

    <div class="stats-grid">
      <div class="stat-box">
        <div class="stat-value easy">{easy}</div>
        <div class="stat-label">Easy</div>
      </div>
      <div class="stat-box">
        <div class="stat-value medium">{medium}</div>
        <div class="stat-label">Medium</div>
      </div>
      <div class="stat-box">
        <div class="stat-value hard">{hard}</div>
        <div class="stat-label">Hard</div>
      </div>
      <div class="stat-box">
        <div class="stat-value total">{total}</div>
        <div class="stat-label">Total</div>
      </div>
    </div>
  </div>

  <!-- Animated Heatmap -->
  <div class="heatmap-section">
    <h3>📅 Submission Activity &nbsp;<span style="color:var(--muted);font-weight:400;font-size:.875rem">{cur_year}</span></h3>
    <img src="{heatmap_data}" alt="Submission heatmap" class="heatmap-img">
  </div>

  <!-- Endpoints -->
  <div class="endpoints-title">📡 API Endpoints</div>

  <div class="endpoint" style="animation-delay:.05s">
    <span class="method get">GET</span><code>/health</code>
    <p>Health check endpoint</p>
  </div>
  <div class="endpoint" style="animation-delay:.08s">
    <span class="method get">GET</span><code>/api/status</code>
    <p>Complete API information and status</p>
  </div>
  <div class="endpoint" style="animation-delay:.11s">
    <span class="method get">GET</span><code>/api/profile</code>
    <p>👤 Get user profile with avatar and submission stats</p>
  </div>
  <div class="endpoint" style="animation-delay:.14s">
    <span class="method get">GET</span><code>/api/heatmap.svg?year={cur_year}</code>
    <p>📊 Animated submission heatmap SVG — embed anywhere with <code>&lt;img&gt;</code></p>
  </div>
  <div class="endpoint" style="animation-delay:.17s">
    <span class="method get">GET</span><code>/api/heatmap/data?year={cur_year}</code>
    <p>Raw heatmap day-counts + streak data as JSON</p>
  </div>
  <div class="endpoint" style="animation-delay:.20s">
    <span class="method get">GET</span><code>/api/submissions?limit=10</code>
    <p>Get fresh submissions from LeetCode API</p>
  </div>
  <div class="endpoint" style="animation-delay:.23s">
    <span class="method get">GET</span><code>/api/submissions/all?limit=100</code>
    <p>🗄️ Get ALL submissions from local database ({db_total} total)</p>
  </div>
  <div class="endpoint" style="animation-delay:.26s">
    <span class="method get">GET</span><code>/api/submissions/recent?hours=24</code>
    <p>Get submissions from last N hours</p>
  </div>
  <div class="endpoint" style="animation-delay:.29s">
    <span class="method post">POST</span><code>/api/submissions/fetch-recent</code>
    <p>Fetch fresh submissions with custom limit<br>
       <small>Body: <code>{{"limit": 50}}</code></small></p>
  </div>
  <div class="endpoint" style="animation-delay:.32s">
    <span class="method post">POST</span><code>/api/submissions/update</code>
    <p>⚡ Manually update local database with recent submissions</p>
  </div>
  <div class="endpoint" style="animation-delay:.35s">
    <span class="method get">GET</span><code>/api/refresh</code>
    <p>🔄 Simple refresh endpoint</p>
  </div>
  <div class="endpoint" style="animation-delay:.38s">
    <span class="method get">GET</span><code>/api/submissions/download</code>
    <p>📥 Download complete submissions database as JSON file</p>
  </div>
  <div class="endpoint" style="animation-delay:.41s">
    <span class="method get">GET</span><code>/api/github/status</code>
    <p>🔒 Check GitHub integration status for persistent storage</p>
  </div>

  {warn_block}

  <div class="footer">
    <p>🌐 Powered by Vercel Serverless Functions</p>
    <p>⏰ Database auto-updates every hour &nbsp;|&nbsp; {db_total} submissions stored</p>
  </div>

</body>
</html>'''

    # Return JSON for API calls
    github_status = {
        "enabled": bool(GITHUB_TOKEN),
        "repository": GITHUB_REPO,
        "branch": GITHUB_BRANCH
    }

    # Include persistence warning if GitHub integration is not enabled
    persistence_info = []

    if not GITHUB_TOKEN:
        persistence_info = [
            "⚠️ GitHub integration NOT enabled - updates will not persist",
            "Set GITHUB_TOKEN in Vercel environment variables for persistent storage",
            "See /api/github/status for setup instructions"
        ]
    
    return jsonify({
        "message": "LeetCode Submissions API (Vercel Serverless)",
        "version": "3.0.0",
        "description": "Serverless API for LeetCode submissions using public endpoints",
        "username": LEETCODE_USERNAME,
        "platform": "vercel",
        "database": {
            "total_submissions": len(leetcode_api.all_submissions),
            "last_update": leetcode_api.last_update.isoformat() if leetcode_api.last_update else None,
            "auto_update_interval": f"{leetcode_api.update_interval//3600} hour(s)"
        },
        "persistence": github_status,
        "features": [
            "Serverless functions",
            "No authentication required",
            "Fresh data on every request",
            "Uses LeetCode public API",
            "GitHub integration for persistent storage",
            "Hourly automated updates"
        ],
        "persistence_warnings": persistence_info,
        "endpoints": {
            "GET /api/submissions": "Get fresh submissions from LeetCode API",
            "GET /api/submissions/all": "Get all submissions from local database",
            "GET /api/submissions/recent": "Get submissions from last N hours",
            "POST /api/submissions/fetch-recent": "Fetch with custom limit",
            "GET /api/refresh": "Simple refresh endpoint",
            "POST /api/submissions/update": "Update local database manually",
            "GET /api/submissions/download": "Download complete database",
            "GET /api/github/status": "Check GitHub integration status",
            "GET /api/status": "API status and info"
        },
        "usage": {
            "all_submissions": "GET /api/submissions/all?limit=100",
            "fresh_api": "GET /api/submissions?limit=10",
            "recent_filter": "GET /api/submissions/recent?hours=6&limit=20",
            "manual_update": "GET /api/refresh",
            "download": "GET /api/submissions/download",
            "github_status": "GET /api/github/status"
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "platform": "vercel",
        "timestamp": get_ist_now().isoformat(),
        "version": "3.0.0",
        "username": LEETCODE_USERNAME
    })


@app.route('/api/heatmap', methods=['GET'])
@app.route('/api/heatmap.svg', methods=['GET'])
def get_heatmap():
    """Return an animated SVG submission heatmap for the given year."""
    try:
        year     = request.args.get('year',     get_ist_now().year, type=int)
        username = request.args.get('username', LEETCODE_USERNAME)

        counts             = build_day_counts(leetcode_api.all_submissions, year)
        total_submissions  = sum(counts.values())
        streak, longest    = calculate_streak(counts, year)

        svg = generate_heatmap_svg(
            username, year, counts, total_submissions, streak, longest
        )

        return Response(
            svg,
            mimetype='image/svg+xml',
            headers={
                'Cache-Control': 'public, max-age=1800',
                'Content-Type':  'image/svg+xml; charset=utf-8',
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/heatmap/data', methods=['GET'])
def get_heatmap_data():
    """Return raw heatmap data (day counts + streak) as JSON."""
    try:
        year   = request.args.get('year', get_ist_now().year, type=int)
        counts = build_day_counts(leetcode_api.all_submissions, year)
        streak, longest = calculate_streak(counts, year)

        return jsonify({
            "success": True,
            "year": year,
            "username": LEETCODE_USERNAME,
            "total_submissions": sum(counts.values()),
            "streak": streak,
            "longest_streak": longest,
            "data": [{"date": d, "count": c} for d, c in sorted(counts.items())]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Get user profile information including avatar"""
    try:
        profile = leetcode_api.fetch_user_profile()
        
        if not profile:
            return jsonify({
                "success": False,
                "message": "Could not fetch user profile",
                "username": LEETCODE_USERNAME
            }), 404
            
        return jsonify({
            "success": True,
            "profile": profile
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/profile/details', methods=['GET'])
def get_profile_details():
    """Get detailed user profile from all available sources"""
    try:
        # Get data from all sources separately for comparison
        leetcode_data = leetcode_api._fetch_from_leetcode_graphql()
        external_data = leetcode_api._fetch_from_external_apis()
        merged_data = leetcode_api._merge_profile_data(leetcode_data, external_data)
        
        return jsonify({
            "success": True,
            "leetcode_graphql": leetcode_data,
            "external_apis": external_data,
            "merged_profile": merged_data,
            "username": LEETCODE_USERNAME,
            "apis_used": leetcode_api.external_apis
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
        
@app.route('/api/status/apis', methods=['GET'])
def get_api_status():
    """Check the status of all external APIs"""
    try:
        status = leetcode_api.check_api_status()
        
        # Calculate overall availability
        all_apis = [status["leetcode_graphql"]] + [api["status"] for name, api in status["external_apis"].items()]
        availability_percentage = int((sum(1 for status in all_apis if status) / len(all_apis)) * 100)
        
        return jsonify({
            "success": True,
            "status": status,
            "availability_percentage": availability_percentage,
            "timestamp": get_ist_now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/github/status', methods=['GET'])
def github_status():
    """Check GitHub integration status"""
    try:
        github_enabled = bool(GITHUB_TOKEN)
        integration_message = "GitHub integration enabled" if github_enabled else "GitHub integration disabled - set GITHUB_TOKEN in environment variables"
        
        # Test GitHub connection if enabled
        github_connection = False
        test_result = None
        if github_enabled:
            try:
                headers = {
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
                response = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}", headers=headers)
                github_connection = response.status_code == 200
                if github_connection:
                    repo_data = response.json()
                    test_result = {
                        "repository": repo_data.get("full_name"),
                        "owner": repo_data.get("owner", {}).get("login"),
                        "default_branch": repo_data.get("default_branch"),
                        "permissions": repo_data.get("permissions")
                    }
                else:
                    test_result = {
                        "status_code": response.status_code,
                        "message": response.text
                    }
            except Exception as e:
                test_result = {"error": str(e)}
        
        return jsonify({
            "github_integration_enabled": github_enabled,
            "message": integration_message,
            "repository": GITHUB_REPO,
            "branch": GITHUB_BRANCH,
            "connection_test": {
                "success": github_connection,
                "result": test_result
            },
            "setup_instructions": "To enable GitHub integration for persistent storage, add GITHUB_TOKEN, GITHUB_REPO and GITHUB_BRANCH to your Vercel environment variables.",
            "timestamp": get_ist_now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/favicon.ico')
def favicon():
    """Serve favicon - fallback route"""
    try:
        # Try to serve favicon from public directory
        favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public', 'favicon.ico')
        if os.path.exists(favicon_path):
            return send_file(favicon_path, mimetype='image/vnd.microsoft.icon')
    except Exception:
        pass
    
    # Return empty response if not found
    return '', 204

# Export the app for Vercel
app = app

if __name__ == "__main__":
    app.run(debug=True)
