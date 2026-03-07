# 🚀 LeetCode API - Vercel Serverless

A serverless API to fetch LeetCode submissions using Vercel deployment.

## 🔐 Important Setup for Persistent Updates

**Problem:** Vercel serverless functions cannot persistently update the submissions database.

**Solution:** To enable automatic updates to your GitHub repository (crucial for persistent storage), set up GitHub integration:

1. Create a [GitHub Personal Access Token](https://github.com/settings/tokens) with `repo` permissions
2. Add these environment variables in your Vercel project:
   - `GITHUB_TOKEN`: Your GitHub personal access token
   - `GITHUB_REPO`: Your repository name (e.g., "AHILL-0121/LEETAPI")
   - `GITHUB_BRANCH`: Your branch name (default is "main")

After adding these variables, redeploy your application for the hourly updates and manual refresh triggers to work correctly.

## ✨ Features

- 🔄 **Fresh Data**: Always fetches latest submissions from LeetCode
- 🚀 **Serverless**: No background processes, scales automatically  
- 🔓 **No Auth**: Uses LeetCode public API
- ⚡ **Fast**: Optimized for Vercel edge functions
- 📱 **Simple**: Clean REST API endpoints

## 🚀 Deploy to Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/AHILL-0121/LEETAPI)

### Manual Deployment

1. **Install Vercel CLI**
   ```bash
   npm install -g vercel
   ```

2. **Deploy**
   ```bash
   vercel --prod
   ```

3. **Set Environment Variables** (Optional)
   ```bash
   vercel env add LEETCODE_USERNAME
   ```

## 🌐 API Endpoints

| Endpoint | Method | Description |
|----------|---------|-------------|
| `/` | GET | API documentation |
| `/health` | GET | Health check |
| `/api/status` | GET | API status & info |
| `/api/submissions` | GET | Get recent submissions |
| `/api/submissions/recent` | GET | Get submissions from last N hours |
| `/api/submissions/fetch-recent` | POST | Fetch with custom limit |
| `/api/heatmap.svg` | GET | Get animated contribution heatmap (supports light/dark theme) |
| `/api/heatmap/data` | GET | Get raw heatmap data as JSON |

## 🔧 Usage Examples

```bash
# Get latest 10 submissions
GET /api/submissions?limit=10

# Get submissions from last 6 hours
GET /api/submissions/recent?hours=6&limit=20

# Fetch custom amount
POST /api/submissions/fetch-recent
{"limit": 100}

# Get heatmap SVG for current year (light theme - default)
GET /api/heatmap.svg

# Get heatmap SVG with dark theme
GET /api/heatmap.svg?theme=dark

# Get heatmap for specific year with dark theme
GET /api/heatmap.svg?year=2025&theme=dark

# Get raw heatmap data as JSON
GET /api/heatmap/data?year=2025
```

## 🔧 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LEETCODE_USERNAME` | No | `ahillselvaraaj` | Your LeetCode username |

## 📊 Response Format

```json
{
  "success": true,
  "count": 10,
  "platform": "vercel",
  "data": [
    {
      "id": "123456789",
      "title": "Two Sum",
      "titleSlug": "two-sum",
      "timestamp": "1640995200",
      "submissionDate": "2022-01-01 00:00:00",
      "url": "https://leetcode.com/problems/two-sum/"
    }
  ]
}
```

## 🎯 Vercel Optimizations

- ✅ **No Background Tasks**: Removed scheduler/threading
- ✅ **Stateless**: Fresh data on every request
- ✅ **Minimal Dependencies**: Only requests + flask
- ✅ **Fast Cold Starts**: Optimized imports
- ✅ **Edge Compatible**: Works on Vercel edge runtime

## 📋 Project Structure

```
├── api/
│   └── index.py          # Main serverless function
├── .gitignore           # Git ignore rules
├── README.md           # This file
├── requirements.txt    # Python dependencies
└── vercel.json        # Vercel configuration
```

## 🔄 Migration from Render

This version is optimized for Vercel serverless architecture:

- **Removed**: Background scheduler, file persistence, complex caching
- **Added**: Fresh data fetching, simplified endpoints
- **Kept**: All core API functionality, public LeetCode API integration

## 📄 License

MIT License - feel free to use and modify!