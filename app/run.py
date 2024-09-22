import uvicorn
import os
from fastapi import FastAPI, Request, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from parse import scan_file, find_type
from network import scan_network
# from disk import scan_disk
# from memory import scan_memory
# from registry import scan_registry
# from process import scan_process
from drive import scan_drive
from gemini import predict, summarize

from models.risk.risk_level import predict_level
from models.risk.risk_type import predict_type
from models.network_traffic.network import predict_network

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
    allow_credentials=True
)

@app.get('/')
async def root():
    return JSONResponse(content={'message': 'Backend server is running.'})

@app.post('/api/analyze')
async def analyze(uploadedFiles: list[UploadFile] = File(...), yaraFile: UploadFile = File(...)):
    # Initialize list to store scan results and create temporary directory
    scan_results = []
    TEMP_DIR = 'temp'
    os.makedirs(TEMP_DIR, exist_ok=True)

    try:
        # Save YARA rules file to temporary directory
        rules_path = os.path.join(TEMP_DIR, yaraFile.filename)
        with open(rules_path, 'wb') as f:
            f.write(await yaraFile.read())

        # Scan each uploaded file to temporary directory
        for file in uploadedFiles:
            file_path = os.path.normpath(os.path.join(TEMP_DIR, file.filename))
            file_directory  = os.path.dirname(file_path)
            os.makedirs(file_directory , exist_ok=True)

            with open(file_path, 'wb') as f:
                f.write(await file.read())

            # Determine file type and scan file based on type
            file_type = find_type(file_path)
            if file_type == 'text':
                file_data = scan_file(file_path, rules_path, file_type)
                rule_counts = {} # Initialize dictionary to store rule counts

                # Count the number of times each rule was triggered in the file
                for data in file_data:
                    rule_name = data['triggered_action']
                    # Check if rule is already in dictionary and increment count
                    if rule_name in rule_counts:
                        rule_counts[rule_name] += 1
                    else:
                        rule_counts[rule_name] = 1

                # Append text scan results to scan_results list as dictionary
                scan_results.append({
                    'file': os.path.basename(file_path),
                    'yara': rule_counts,
                    'risk_level': predict_level(rule_name),
                    'risk_type': predict_type(rule_name),
                    'vulnerability_type': 'Text File',
                    'vulnerability_count': sum(rule_counts.values())
                })

            elif file_type == 'network':
                network_data = scan_network(file_path)
                # Append network scan results to scan_results list as dictionary
                scan_results.append({
                    'file': os.path.basename(file_path),
                    'network': network_data,
                    'risk_level': 'High',
                    'risk_type': predict_network(network_data),
                    'vulnerability_type': 'Network Traffic',
                    'vulnerability_count': len(network_data)
                })

            elif file_type == 'disk':
                disk_data = scan_disk(file_path, rules_path)
                for data in disk_data:
                    for rule_name in data['triggered_action']:
                        # Append disk scan results to scan_results list as dictionary
                        scan_results.append({
                            'file': os.path.basename(file_path),
                            'disk': disk_data,
                            'risk_level': predict_level(rule_name),
                            'risk_type': predict_type(rule_name),
                            'vulnerability_type': 'Disk Image',
                            'vulnerability_count': len(data)
                        })

            elif file_type == 'memory':
                memory_data = scan_memory(file_path, rules_path)
                # Append memory scan results to scan_results list as dictionary
                scan_results.append({
                    'file': os.path.basename(file_path),
                    'memory': memory_data,
                    'risk_level': predict_level(rule_name),
                    'risk_type': predict_type(rule_name),
                    'vulnerability_type': 'Memory Dump',
                    'vulnerability_count': len(memory_data)
                })

        return JSONResponse(content={
            'results': scan_results,
            'gemini': predict(scan_results, 'Analyze')
        })
    except Exception as e:
        return JSONResponse(content={'error': str(e)})

@app.post('/api/detect')
async def detect(background_tasks: BackgroundTasks):
    # Add scan_drive function to background tasks to look for removable drives
    background_tasks.add_task(scan_drive)
    return JSONResponse(content={'message': 'Drive detection started.'})

@app.get('/api/files')
async def files():
    # Get metadata of all files in the drive
    files_metadata = scan_drive()
    return JSONResponse(content=files_metadata)

@app.get('/api/files/{file_name}')
async def send_file(file_name: str):
    # Send the file based on the file name in the request
    files_metadata = scan_drive()
    file_object = next(
        (file for file in files_metadata if file['name'] == file_name), None
    )

    if file_object is None:
        return JSONResponse(content={'error': 'File not found.'})

    return FileResponse(filename=file_object['name'], path=file_object['path'], media_type='application/octet-stream')

@app.post('/api/download')
async def download(request: Request):
    # Get the file data and type from the request
    request_data = await request.json()
    file_data = request_data.get('data')
    file_type = request_data.get('type')

    # Check the file type and generate a summary
    if file_type == 'PDF':
        file_name = summarize(file_data, 'Summarize')
        pdf_path = os.path.join(os.getcwd(), file_name)
        return FileResponse(filename=file_name, path=pdf_path, media_type='application/pdf')

    return JSONResponse(content={'error': 'Unsupported file type.'})

@app.post('/api/export')
async def export():
    pass

@app.post('/api/chat')
async def chat(request: Request):
    # Get the user message from the request
    request_data = await request.json()
    user_message = request_data.get('message')

    # Get the response from the Gemini model
    bot_response = predict(user_message, 'Chat')
    return JSONResponse(content={'response': bot_response})

if __name__ == '__main__':
    uvicorn.run('run:app', host='0.0.0.0', port=8000, reload=True)
