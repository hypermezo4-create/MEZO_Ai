class MFAService:
    def verify_otp(self, user_id: str, otp: str) -> bool:
        return len(otp) == 6
