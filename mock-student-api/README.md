# Mock Student Database API

⚠️ **DEVELOPMENT/TESTING ONLY** ⚠️

A Docker-based mock API that simulates the student database for development and testing purposes. **This should NEVER be used in production environments.**

## Features

- RESTful API with realistic mock student data
- Multiple semester records per student showing academic progression
- Comprehensive student information matching the production schema
- Docker containerized for easy deployment
- SQLite database with automatically generated sample data
- API documentation with Swagger/OpenAPI

## API Endpoints

### Student Information
- `GET /api/students/{student_id}` - Get complete student information
- `GET /api/students` - List students with pagination

### Semester Information
- `GET /api/students/{student_id}/semesters` - Get all semester records for a student
- `GET /api/students/{student_id}/semesters?year={year}&term={term}` - Filter by year/term
- `GET /api/semesters?student_id={student_id}` - Alternative endpoint format
- `GET /api/students/{student_id}/semesters/{year}/{term}` - Get specific semester

### Utility
- `GET /` - API information and endpoint list
- `GET /health` - Health check endpoint
- `GET /docs` - Interactive API documentation (Swagger UI)

## Quick Start

### Using Docker Compose (Recommended)

For development environment:
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
docker run -p 8080:8080 -v $(pwd)/data:/app/data mock-student-api
```

### Local Development

```bash
cd mock-student-api
pip install -r requirements.txt
python main.py
```

## Sample Data

The API automatically generates 100 mock students with:

- Realistic Chinese and English names
- Various degree programs (PhD, Master's, Bachelor's)
- Multiple academic departments and colleges
- Progressive semester records showing academic history
- Different student statuses and identity types
- Contact information and enrollment details

### Student Information Schema

```json
{
  "std_stdno": "123456789",
  "std_stdcode": "123456789", 
  "std_pid": "A123456789",
  "std_cname": "王小明",
  "std_ename": "Ming Wang",
  "std_degree": 2,
  "std_studingstatus": 1,
  "std_nation1": "ROC",
  "std_nation2": null,
  "std_schoolid": 1,
  "std_identity": 1,
  "std_termcount": 4,
  "std_depno": "CS",
  "dep_depname": "資訊工程學系",
  "std_academyno": "EECS",
  "aca_cname": "電機資訊學院",
  "std_enrolltype": 1,
  "std_directmemo": null,
  "std_highestschname": "台灣大學電機系",
  "com_cellphone": "0912345678",
  "com_email": "ming.wang@gmail.com",
  "com_commzip": "106",
  "com_commadd": "台北市中正區中山路123號",
  "std_sex": 1,
  "std_enrollyear": 112,
  "std_enrollterm": 1,
  "enrollment_date": "2023-09-01"
}
```

### Semester Records Schema

```json
{
  "student_id": "123456789",
  "semesters": [
    {
      "trm_year": 112,
      "trm_term": 1,
      "trm_stdno": "123456789",
      "trm_studystatus": 1,
      "trm_ascore": 85.5,
      "trm_termcount": 1,
      "grade_level": 1,
      "trm_degree": 2,
      "trm_academyname": "電機資訊學院",
      "trm_depname": "資訊工程學系",
      "trm_ascore_gpa": 3.4,
      "trm_stdascore": 85.5,
      "trm_placingsrate": 15,
      "trm_depplacingrate": 45
    }
  ]
}
```

## Reference Data

### Degree Types (`std_degree`)
- `1`: PhD (博士)
- `2`: Master's (碩士) 
- `3`: Bachelor's (大學)

### Study Status (`std_studingstatus`, `trm_studystatus`)
- `1`: Enrolled (在學)
- `2`: Should Graduate (應畢)
- `3`: Extended Study (延畢)
- `4`: Leave of Absence (休學)
- `11`: Graduated (畢業)

### Student Identity Categories (`std_identity`)
- `1`: Regular (一般生)
- `2`: Indigenous (原住民)
- `3`: Overseas Chinese with ROC citizenship (僑生)
- `17`: Mainland Chinese student (陸生)
- `30`: Other (其他)

### Gender (`std_sex`)
- `1`: Male (男)
- `2`: Female (女)

## Testing the API

```bash
# Get student information
curl http://localhost:8080/api/students/123456789

# Get semester records
curl http://localhost:8080/api/students/123456789/semesters

# Filter by year and term
curl "http://localhost:8080/api/students/123456789/semesters?year=113&term=1"

# Health check
curl http://localhost:8080/health

# List students
curl http://localhost:8080/api/students
```

## Development Notes

- The database is automatically initialized with sample data on first run
- Data is persisted in the `data/` directory
- No real personal information is stored - all data is generated
- Each student has realistic semester progression showing academic history
- API includes proper error handling and validation
- All endpoints return appropriate HTTP status codes

## Configuration

Environment variables:
- `PYTHONUNBUFFERED=1` - For proper Docker logging

## API Documentation

Visit `http://localhost:8080/docs` for interactive Swagger UI documentation.