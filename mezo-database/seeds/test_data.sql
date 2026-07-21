INSERT INTO skills (name, category, description) 
VALUES ('file_management', 'system-skills', 'إدارة الملفات في مسار العمل')
ON CONFLICT DO NOTHING;
