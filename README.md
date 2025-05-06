# Threads Traffic Management System

A Python-based system for driving traffic to a main Threads account through coordinated bot activities.

## Components

1. **Scraper Module**: Discovers trending posts and extracts engagement metrics
2. **Follow Bot Module**: Increases profile visibility through targeted following
3. **Reply Bot Module**: Generates AI-driven engagement through contextual comments
4. **Orchestration Layer**: Coordinates bot activities and tracks effectiveness

## Setup Instructions

### Prerequisites

- Python 3.10+
- Docker and Docker Compose (for deployment)
- Dolphin Anty for proxy management
- OpenAI API or DeepSeek API key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ThreadTrafficManagementSystem.git
cd ThreadTrafficManagementSystem
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your API keys and configuration:
```bash
cp .env.example .env
# Edit .env with your credentials
```

5. Initialize the database:
```bash
python database/init_db.py
```

### Running the System

```bash
python main.py
```

For the monitoring dashboard:
```bash
streamlit run dashboard.py
```

## Configuration

Edit `config/settings.py` to modify system parameters:
- Account limits
- Rate limits
- Proxy configuration
- AI model settings

## Deployment

```bash
docker-compose up -d
```

## Safety Features

- Randomized user agents and browser fingerprints
- Variable timing between operations
- Human-like interaction patterns
- IP rotation
- Account warm-up procedures

## Performance

- Handles 20+ bot accounts simultaneously
- Processes 100+ trending posts daily
- Generates 500+ AI replies daily
- Low resource utilization 


image.png