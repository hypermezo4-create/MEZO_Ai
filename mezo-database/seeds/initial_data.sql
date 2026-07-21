INSERT INTO users (username, email, password_hash, role) 
VALUES ('mezo_admin', 'admin@mezo.ai', '$2b$10$e7K4V5m1xX8qH5y6Z9W0u.G5A5N5O5P5Q5R5S5T5U5V5W5X5Y5Z', 'admin')
ON CONFLICT DO NOTHING;
