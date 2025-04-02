# from flask import Flask, request, redirect, url_for, render_template, flash
# from azure.storage.blob import BlobServiceClient
# import os
# import re
# from dotenv import load_dotenv

# # Load environment variables
# load_dotenv()

# app = Flask(__name__)
# app.secret_key = "dev-key-123"  # Simple key for development only

# # Azure Blob Storage setup
# connection_string = os.getenv("AZURE_CONNECTION_STRING")
# container_name = "user-files"
# blob_service_client = BlobServiceClient.from_connection_string(connection_string)
# container_client = blob_service_client.get_container_client(container_name)

# def sanitize_filename(filename):
#     """Sanitize filename for Azure Blob Storage"""
#     # Remove special characters but keep ._- 
#     safe_name = re.sub(r'[^a-zA-Z0-9\-_.]', '_', filename)
#     # Remove leading/trailing special chars
#     safe_name = safe_name.strip("._-")
#     # Truncate to Azure's 1024 char limit
#     return safe_name[:1024]

# @app.route("/")
# def index():
#     return render_template("index.html")

# @app.route("/upload", methods=["POST"])
# def upload():
#     if "file" not in request.files:
#         flash("No file selected", "error")
#         return redirect(url_for("index"))
    
#     file = request.files["file"]
#     if file.filename == "":
#         flash("Empty file", "error")
#         return redirect(url_for("index"))
    
#     try:
#         safe_name = sanitize_filename(file.filename)
#         blob_client = container_client.get_blob_client(safe_name)
#         blob_client.upload_blob(file, overwrite=True)
#         flash(f"'{safe_name}' uploaded successfully!", "success")
#     except Exception as e:
#         flash(f"Upload failed: {str(e)}", "error")
    
#     return redirect(url_for("list_files"))

# @app.route("/files")
# def list_files():
#     try:
#         blobs = container_client.list_blobs()
#         return render_template("files.html", blobs=blobs)
#     except Exception as e:
#         flash(f"Error: {str(e)}", "error")
#         return redirect(url_for("index"))

# @app.route("/download/<filename>")
# def download(filename):
#     try:
#         blob_client = container_client.get_blob_client(filename)
#         if not os.path.exists('downloads'):
#             os.makedirs('downloads')
#         with open(f"downloads/{filename}", "wb") as f:
#             f.write(blob_client.download_blob().readall())
#         flash(f"Downloaded: {filename}", "success")
#     except Exception as e:
#         flash(f"Download failed: {str(e)}", "error")
#     return redirect(url_for("list_files"))

# if __name__ == "__main__":
#     app.run(debug=True)

from flask import Flask, request, redirect, url_for, render_template, flash, send_file, session
from azure.storage.blob import BlobServiceClient
import os
import io
from dotenv import load_dotenv
from datetime import datetime
import mimetypes
import pytz  # Add this import at the top

load_dotenv()

app = Flask(__name__)
app.secret_key = "dev-secret-key"

# Azure setup
connection_string = os.getenv("AZURE_CONNECTION_STRING")
container_name = "user-files"
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
container_client = blob_service_client.get_container_client(container_name)

def format_datetime(timestamp):
    if not timestamp:
        return "N/A"
    
    # Define your local timezone (e.g., Asia/Kolkata for India)
    local_tz = pytz.timezone("Asia/Kolkata")  # Change this to your timezone
    
    # Convert timestamp from UTC to local timezone
    utc_time = timestamp.replace(tzinfo=pytz.utc)
    local_time = utc_time.astimezone(local_tz)
    
    return local_time.strftime("%Y-%m-%d %H:%M:%S")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    """Simulated login to store user email in session."""
    email = request.form.get("email")
    if email:
        session["user_email"] = email
        flash(f"Logged in as {email}", "success")
    return redirect("/files")

@app.route("/logout")
def logout():
    session.pop("user_email", None)
    flash("Logged out successfully", "success")
    return redirect("/")

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("No file selected", "error")
        return redirect("/")

    file = request.files["file"]
    if file.filename == "":
        flash("No file selected", "error")
        return redirect("/")

    try:
        user_email = session.get("user_email", "guest")  # Organize files by user
        blob_path = f"{user_email}/{file.filename}"  # Store inside user folder
        blob_client = container_client.get_blob_client(blob_path)

        # Upload with versioning (creates a new version if the file exists)
        blob_client.upload_blob(file, overwrite=False)  

        flash(f"'{file.filename}' uploaded successfully! New version created.", "success")
    except Exception as e:
        flash(f"Upload failed: {str(e)}", "error")

    return redirect("/files")


@app.route("/files")
def list_files():
    """Lists files with version history, grouped by user."""
    user_email = session.get("user_email", "guest")  
    try:
        blobs = list(container_client.list_blobs(name_starts_with=f"{user_email}/", include=['versions']))
        
        files = []
        for blob in blobs:
            if not blob.is_current_version:
                continue  # Skip non-current versions in main listing

            versions = []
            if blob.version_id:  
                versions_blobs = container_client.list_blobs(name_starts_with=blob.name, include=['versions'])
                for version_blob in versions_blobs:
                    if version_blob.name == blob.name:
                        versions.append({
                            'version_id': version_blob.version_id,
                            'last_modified': format_datetime(version_blob.last_modified) if version_blob.last_modified else "N/A",
                            'size': version_blob.size,
                            'is_current': version_blob.is_current_version
                        })
            
            files.append({
                'name': blob.name.split("/")[-1],  
                'path': blob.name,  
                'last_modified': format_datetime(blob.last_modified) if blob.last_modified else "N/A",
                'size': blob.size,
                'versions': versions
            })
        
        return render_template("files.html", files=files)
    except Exception as e:
        flash(f"Error listing files: {str(e)}", "error")
        return redirect("/")

@app.route("/download/<path:blob_path>")
def download(blob_path, version_id=None):
    try:
        blob_client = container_client.get_blob_client(blob_path)
        if version_id:
            blob_client = blob_client.get_blob_client(version_id=version_id)
        
        download_stream = blob_client.download_blob()
        return send_file(
            io.BytesIO(download_stream.readall()),
            as_attachment=True,
            download_name=blob_path.split("/")[-1]
        )
    except Exception as e:
        flash(f"Download failed: {str(e)}", "error")
        return redirect("/files")

@app.route("/download_version/<path:blob_path>/<version_id>")
def download_version(blob_path, version_id):
    try:
        # Ensure we use the correct BlobClient method
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        
        # Download a specific version
        blob_data = blob_client.download_blob(version_id=version_id)
        file_data = blob_data.readall()

        # Get the file name from the blob path
        filename = blob_path.split("/")[-1]

        # Send the file to the user for download
        return send_file(
            io.BytesIO(file_data),
            as_attachment=True,
            download_name=filename,
            mimetype="application/octet-stream"
        )

    except Exception as e:
        flash(f"Download failed: {str(e)}", "error")
        return redirect(url_for("files"))


@app.route("/preview/<path:blob_path>")
def preview(blob_path):
    """Allows previewing images, PDFs, and text files from Azure Blob Storage."""
    try:
        # Get blob client
        blob_client = blob_service_client.get_blob_client(container_name, blob_path)
        download_stream = blob_client.download_blob()
        file_data = download_stream.readall()

        # Determine the file's MIME type
        mime_type, _ = mimetypes.guess_type(blob_path)
        if not mime_type:
            mime_type = "application/octet-stream"  # Default binary type

        # Return the file for inline preview
        return send_file(
            io.BytesIO(file_data),
            mimetype=mime_type,
            as_attachment=False  # Ensures inline viewing
        )

    except Exception as e:
        flash(f"Preview failed: {str(e)}", "error")
        return redirect("/files")  # Redirect to the file list page

@app.route("/delete/<path:blob_path>", methods=["POST"])
def delete(blob_path):
    try:
        print(f"Deleting blob: {blob_path}")  # Debugging line

        blob_client = container_client.get_blob_client(blob_path)

        # Check if the blob exists before attempting to delete
        if not blob_client.exists():
            flash(f"Delete failed: The specified file does not exist.", "error")
            return redirect("/files")

        # Delete all versions and snapshots if they exist
        blob_client.delete_blob(delete_snapshots="include")

        flash(f"'{blob_path.split('/')[-1]}' and all its versions deleted successfully!", "success")
    except Exception as e:
        flash(f"Delete failed: {str(e)}", "error")
    
    return redirect("/files")




if __name__ == "__main__":
    app.run(debug=True)


