provider "aws" {
  region = var.aws_region
}

resource "aws_instance" "mezo_server" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = var.instance_type

  tags = {
    Name = "MEZO-AI-Platform-Server"
  }
}
