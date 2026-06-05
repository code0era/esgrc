# ESGRC Intelligence Platform

The **ESGRC Intelligence Platform** is an enterprise-grade Streamlit application designed for Environmental, Social, Governance, Risk, and Compliance (ESGRC) performance analysis and AI-driven reporting.

## Features

- **Secure Authentication**: User login and registration, securely storing data in a local database.
- **Data Ingestion**: Upload metric values (CSV) and configuration definitions (JSON) to evaluate ESG performance.
- **Performance Evaluation**: Automatically calculates weighted averages and identifies low-performing metrics, groups, and sub-modules.
- **AI-Driven Insights**: Leverages Anthropic's Claude to generate comprehensive executive summaries based on your specific ESG data.
- **Professional Reporting**: View scores on an intuitive dashboard and export detailed performance reports directly to PDF.
- **Interactive AI Chat**: A built-in AI assistant panel to answer questions about the generated report and provide actionable ESG and compliance advice.

## Tech Stack

- **Frontend/App Framework**: Streamlit
- **AI Integration**: Anthropic Claude API (`anthropic`)
- **Database**: MongoDB (`pymongo`)
- **Data Processing**: Pandas, NumPy
- **Security**: `bcrypt` for password hashing
- **Reporting**: `reportlab` for PDF generation

## Prerequisites

- Python 3.8+
- MongoDB (running locally or accessible via connection string)
- Anthropic API Key

## Setup & Installation

1. **Clone the repository** (if applicable) and navigate to the project directory:
   ```bash
   cd esgrc-streamlit
   ```

2. **Install the required dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Secrets**:
   Create a `.streamlit/secrets.toml` file in the root directory (or use `.env` if preferred, depending on your setup) and add your Anthropic API key:
   ```toml
   ANTHROPIC_API_KEY = "your-anthropic-api-key"
   ```

4. **Ensure MongoDB is running** on your local machine (default port 27017) or update the database connection URI in the utils.

5. **Run the application**:
   ```bash
   streamlit run app.py
   ```

## Usage

1. Open the app in your browser (usually `http://localhost:8501`).
2. Create an account or sign in.
3. Upload your Metric CSV File and Config JSON File.
4. Click **Generate Report** to analyze the data.
5. Review your scores, download the PDF report, or interact with the AI assistant in the right panel for deeper insights.
