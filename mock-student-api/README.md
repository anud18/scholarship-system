# Mock Student Database API with HMAC-SHA256 Authentication

⚠️ **DEVELOPMENT/TESTING ONLY** ⚠️

A Docker-based mock API that simulates the university's student information system with HMAC-SHA256 authentication for development and testing purposes. **This should NEVER be used in production environments.**

## Features

- **HMAC-SHA256 Authentication** - Full signature verification compatible with university API
- **Exact API Endpoints** - `/getsoaascholarshipstudent` and `/getsoaascholarshipstudentterm`
- **Strict/Loose Verification Modes** - Configurable time and encoding validation
- **Realistic Sample Data** - Chinese academic system with sample student `313612215`
- **Complete Error Handling** - Proper authentication rejection and validation
- **Docker Containerized** - Easy deployment and testing

## Authentication

### HMAC-SHA256 Signature Verification

The API implements the university's authentication specification:

```
Authorization: HMAC-SHA256:<TIME>:<ACCOUNT>:<SIGNATURE_HEX>
Content-Type: application/json;charset=UTF-8
ENCODE_TYPE: UTF-8
```

**Signature Calculation:**
1. **Message** = `<TIME>` + `<REQUEST_JSON>` (no spaces, compact JSON)
2. **Signature** = `HMAC-SHA256(key=HEX_BYTES, msg=Message)` → lowercase hex
3. **Time Format** = `YYYYMMDDHHMMSS` (14 digits)

### Environment Configuration

```bash
# HMAC key (hex format)
MOCK_HMAC_KEY_HEX=4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a

# Verification modes
STRICT_TIME_CHECK=true          # Enable ±5 minute time validation
STRICT_ENCODE_CHECK=false       # Require ENCODE_TYPE header
TIME_TOLERANCE_MINUTES=5        # Time tolerance in minutes
```

## API Endpoints

### POST `/getsoaascholarshipstudent`
Get student basic information

**Request:**
```json
{
  "account": "scholarship",
  "action": "qrySoaaScholarshipStudent", 
  "stdcode": "313612215"
}
```

**Response (200):**
```json
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "std_stdno": "A123456789",
      "std_stdcode": "313612215",
      "std_pid": "S125410615",
      "std_cname": "陳弘穎",
      "std_ename": "CHEN,HUNG-YING",
      "std_degree": "3",
      "std_studingstatus": "1",
      "std_nation": "1",
      "std_schoolid": "1",
      "std_identity": "1",
      "std_termcount": "3",
      "std_depno": "EECS01",
      "dep_depname": "電機工程學系",
      "std_academyno": "I",
      "aca_cname": "工學院",
      "std_enrolltype": "1",
      "std_directmemo": "",
      "std_highestschname": "逢甲大學",
      "com_cellphone": "0900000000",
      "com_email": "user@example.com",
      "com_commzip": "300",
      "com_commadd": "新竹市東區大學路100號",
      "std_sex": "1",
      "std_enrollyear": "113",
      "std_enrollterm": "1",
      "std_enrolldate": "2024-09"
    }
  ]
}
```

### POST `/getsoaascholarshipstudentterm`
Get student semester information

**Request:**
```json
{
  "account": "scholarship",
  "action": "qrySoaaScholarshipStudentTerm",
  "stdcode": "313612215",
  "trmyear": "113",
  "trmterm": "2"
}
```

**Response (200):**
```json
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "trm_year": "113",
      "trm_term": "2", 
      "trm_stdno": "313612215",
      "trm_studystatus": "1",
      "trm_ascore": "86.3",
      "trm_termcount": "3",
      "trm_grade": "1",
      "trm_degree": "3",
      "trm_academyname": "工學院",
      "trm_depname": "電機工程學系",
      "trm_ascore_gpa": "3.8",
      "trm_stdascore": "85.1",
      "trm_placingsrate": "20.3",
      "trm_depplacingrate": "25.6"
    }
  ]
}
```

### Utility Endpoints
- `GET /` - API information and configuration
- `GET /health` - Health check with authentication status
- `GET /docs` - Interactive API documentation (Swagger UI)

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Start the main application services first
docker-compose up -d

# Then start the mock student API for development  
docker-compose -f docker-compose.dev.yml up -d mock-student-api
```

Or run standalone:
```bash
cd mock-student-api
docker-compose up -d
```

The API will be available at `http://localhost:8080`

### Using Docker

```bash
cd mock-student-api
docker build -t mock-student-api .
docker run -p 8080:8080 \
  -e MOCK_HMAC_KEY_HEX=4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a \
  -e STRICT_TIME_CHECK=true \
  mock-student-api
```

### Local Development

```bash
cd mock-student-api
pip install -r requirements.txt
export MOCK_HMAC_KEY_HEX=4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a
python main.py
```

## Sample Data

The API includes sample data for testing:

### Available Students
- **313612215** - 陳弘穎 (CHEN,HUNG-YING) - 電機工程學系, 大學生
- **123456789** - 李美麗 (LEE,MEI-LI) - 資訊工程學系, 碩士生

### Sample Data Features
- Realistic Chinese academic system structure
- Multiple semester records per student
- Proper academic progression data
- All required fields from university specification

## Code Reference Tables

### Degree Types (`std_degree`, `trm_degree`)
- `1` - 博士 (PhD)
- `2` - 碩士 (Master's)  
- `3` - 大學 (Bachelor's)

### Study Status (`std_studingstatus`, `trm_studystatus`)
- `1` - 在學 (Enrolled)
- `2` - 應畢 (Should Graduate)
- `3` - 延畢 (Extended Study)
- `4` - 休學 (Leave of Absence)
- `11` - 畢業 (Graduated)

### Student Identity (`std_identity`)
- `1` - 一般生 (Regular)
- `2` - 原住民 (Indigenous)
- `3` - 僑生 (Overseas Chinese)
- `17` - 陸生 (Mainland Chinese)
- `30` - 其他 (Other)

### School Identity (`std_schoolid`)
- `1` - 一般生 (Regular Student)
- `2` - 在職生 (Working Student)
- `3` - 選讀學分 (Credit Student)

### Gender (`std_sex`)
- `1` - 男 (Male)
- `2` - 女 (Female)

## Testing the API

### Automated Test Suite
```bash
# Install test dependencies
pip install requests

# Run comprehensive tests
python test_api.py
```

### Manual Testing with curl
```bash
# Generate HMAC signature (using sample key)
TIME=$(date +%Y%m%d%H%M%S)
ACCOUNT="scholarship"
BODY='{"account":"scholarship","action":"qrySoaaScholarshipStudent","stdcode":"313612215"}'
MESSAGE="${TIME}${BODY}"
KEY="4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a"

# Calculate signature (requires openssl)
SIGNATURE=$(echo -n "$MESSAGE" | openssl dgst -sha256 -mac HMAC -macopt hexkey:$KEY | cut -d' ' -f2)

# Make authenticated request
curl -X POST http://localhost:8080/getsoaascholarshipstudent \
  -H "Authorization: HMAC-SHA256:$TIME:$ACCOUNT:$SIGNATURE" \
  -H "Content-Type: application/json;charset=UTF-8" \
  -H "ENCODE_TYPE: UTF-8" \
  -d "$BODY"
```

### Test Client Example (Python)
```python
import hashlib
import hmac
import json
import requests
from datetime import datetime

def test_api():
    # Configuration
    base_url = "http://localhost:8080"
    hmac_key_hex = "4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a"
    account = "scholarship"
    
    # Create request
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    request_data = {
        "account": account,
        "action": "qrySoaaScholarshipStudent",
        "stdcode": "313612215"
    }
    request_body = json.dumps(request_data, separators=(',', ':'))
    
    # Generate signature
    message = timestamp + request_body
    hmac_key = bytes.fromhex(hmac_key_hex)
    signature = hmac.new(hmac_key, message.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # Make request
    headers = {
        "Authorization": f"HMAC-SHA256:{timestamp}:{account}:{signature}",
        "Content-Type": "application/json;charset=UTF-8",
        "ENCODE_TYPE": "UTF-8"
    }
    
    response = requests.post(f"{base_url}/getsoaascholarshipstudent", 
                           data=request_body, headers=headers)
    print(response.json())

test_api()
```

## Error Responses

### Authentication Errors
- **401** - HMAC signature verification failed
- **422** - Missing required headers

### Validation Errors  
- **400** - Invalid account or action
- **404** - Student or term data not found

### Server Errors
- **500** - Internal server error

## Development Notes

- All data is mock/fake - no real personal information
- HMAC key should be different in production
- Time validation can be disabled for testing (`STRICT_TIME_CHECK=false`)
- Compact JSON format required (no spaces) for signature calculation
- All string fields returned as strings (not numbers) per university API spec
- Supports both strict and loose verification modes for development flexibility

## Security Configuration

### Development Mode (Default)
```bash
STRICT_TIME_CHECK=true
STRICT_ENCODE_CHECK=false
TIME_TOLERANCE_MINUTES=5
```

### Testing Mode (Relaxed)
```bash
STRICT_TIME_CHECK=false
STRICT_ENCODE_CHECK=false
TIME_TOLERANCE_MINUTES=60
```

## API Documentation

Visit `http://localhost:8080/docs` for interactive Swagger UI documentation with authentication examples.