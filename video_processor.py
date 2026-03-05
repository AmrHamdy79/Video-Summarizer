import os
import yt_dlp
import torch
from transformers import pipeline
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from datetime import datetime
from faster_whisper import WhisperModel

class VideoProcessor:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")
        
        self.summarizer = pipeline(
            "summarization",
            model="facebook/bart-large-cnn",
            device=0 if self.device == "cuda" else -1
        )
        
        self.whisper_model = WhisperModel("base", device=self.device, compute_type="int8")
    
    def download_audio(self, video_url, task_id, status_dict):
        status_dict[task_id]['progress'] = 20
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'temp/{task_id}.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'nocheckcertificate': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_title = info.get('title', 'Video Summary')
        
        audio_path = f'temp/{task_id}.mp3'
        return audio_path, video_title
    
    def transcribe_audio(self, audio_path, task_id, status_dict):
        status_dict[task_id]['progress'] = 40
        
        segments, info = self.whisper_model.transcribe(audio_path, beam_size=5)
        
        transcript = ""
        for segment in segments:
            transcript += segment.text + " "
        
        os.remove(audio_path)
        
        return transcript.strip()
    
    def chunk_text(self, text, max_chunk_size=1000):
        sentences = text.replace('\n', ' ').split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) < max_chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def summarize_text(self, text, task_id, status_dict):
        status_dict[task_id]['progress'] = 60
        
        chunks = self.chunk_text(text, max_chunk_size=1000)
        summaries = []
        
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            if len(chunk) < 50:
                continue
            
            try:
                summary = self.summarizer(
                    chunk,
                    max_length=130,
                    min_length=30,
                    do_sample=False
                )
                summaries.append(summary[0]['summary_text'])
            except:
                summaries.append(chunk[:200] + "...")
            
            progress = 60 + int((i + 1) / total_chunks * 20)
            status_dict[task_id]['progress'] = progress
        
        final_summary = " ".join(summaries)
        
        if len(final_summary) > 1500:
            final_summary = self.summarizer(
                final_summary[:4000],
                max_length=500,
                min_length=150,
                do_sample=False
            )[0]['summary_text']
        
        return final_summary
    
    def generate_pdf(self, title, transcript, summary, task_id, status_dict):
        status_dict[task_id]['progress'] = 90
        
        pdf_path = f'temp/{task_id}_summary.pdf'
        doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                                rightMargin=72, leftMargin=72,
                                topMargin=72, bottomMargin=18)
        
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='#2C3E50',
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor='#34495E',
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )
        
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontSize=11,
            textColor='#2C3E50',
            alignment=TA_JUSTIFY,
            spaceAfter=12,
            leading=16
        )
        
        story = []
        
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.2*inch))
        
        date_text = f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        story.append(Paragraph(date_text, styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        story.append(Paragraph("📝 Summary", heading_style))
        story.append(Spacer(1, 0.1*inch))
        
        summary_paragraphs = summary.split('\n')
        for para in summary_paragraphs:
            if para.strip():
                story.append(Paragraph(para, body_style))
        
        story.append(Spacer(1, 0.3*inch))
        story.append(PageBreak())
        
        story.append(Paragraph("🗒️ Full Transcript", heading_style))
        story.append(Spacer(1, 0.1*inch))
        
        transcript_chunks = [transcript[i:i+3000] for i in range(0, len(transcript), 3000)]
        for chunk in transcript_chunks:
            story.append(Paragraph(chunk, body_style))
        
        doc.build(story)
        
        return pdf_path
    
    def process_video(self, video_url, task_id, status_dict):
        audio_path, video_title = self.download_audio(video_url, task_id, status_dict)
        
        transcript = self.transcribe_audio(audio_path, task_id, status_dict)
        
        summary = self.summarize_text(transcript, task_id, status_dict)
        
        pdf_path = self.generate_pdf(video_title, transcript, summary, task_id, status_dict)
        
        return pdf_path