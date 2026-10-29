// Reproduce the hardware cold-start defect: a CTRL write followed immediately by
// beats, the way an AXI DMA issues them.
//
// WHY THIS TOPIC
//
// On the board the first stream after an overlay load loses its first packet
// (849 of 850, err=1463). Every later stream is perfect; a delay before the run
// changes nothing; and even a DMA transfer the module DISCARDS repairs it. So the
// repair is not about data the module processed - it is about the DMA having run
// once.
//
// The difference between a DMA and the existing testbenches:
//
//     tools/tb_stream.v:124   while (!s_axis_tready) @(posedge aclk);
//
// Every testbench waits for TREADY before presenting a beat. A DMA does not. That
// is why 11 simulation suites pass while hardware fails.
//
// THE PREVIOUS VERSION OF THIS FILE WAS WRONG
//
// It reported NORESET-FAIL and I read that as a successful reproduction. It was not:
// a 30-cycle monitor loop sat between the CTRL write and the data loop, draining
// the very window it was meant to observe, and the beat generator never advanced
// (tkeep stuck at FF, tlast never rose). The failure was in the testbench, so the
// "reproduction" proved nothing.
//
// This version drives beats from a forked process CONCURRENT with the control
// write, checks TREADY every cycle, and counts beats offered versus accepted.

`timescale 1ns / 1ps
// CTRL value written before the beat stream. 3 = enable + soft reset in ONE write,
// which is what the driver does. Override to 1 to test enable-only:
//     xvlog --define CTRL_VAL=1 ...
`ifndef CTRL_VAL
`define CTRL_VAL 1
`endif


module tb_no_reset;

    reg         aclk = 0;
    reg         aresetn = 0;
    always #3.0 aclk = ~aclk;

    reg  [4:0]  s_axi_awaddr  = 0;
    reg         s_axi_awvalid = 0;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata   = 0;
    reg  [3:0]  s_axi_wstrb   = 0;
    reg         s_axi_wvalid  = 0;
    wire        s_axi_wready;
    wire [1:0]  s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready  = 1;
    reg  [4:0]  s_axi_araddr  = 0;
    reg         s_axi_arvalid = 0;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready  = 1;

    reg  [63:0] s_axis_tdata  = 0;
    reg  [7:0]  s_axis_tkeep  = 0;
    reg         s_axis_tlast  = 0;
    reg         s_axis_tvalid = 0;
    wire        s_axis_tready;

    wire [7:0]  m_axis_tdata;
    wire        m_axis_tlast;
    wire        m_axis_tvalid;
    reg         m_axis_tready = 1;

    mold64_reasm #(
        .FIFO_AW (12),
        .SESSION (64'h4E41534441513031)
    ) dut (
        .aclk (aclk), .aresetn (aresetn),
        .s_axi_awaddr (s_axi_awaddr), .s_axi_awvalid (s_axi_awvalid),
        .s_axi_awready (s_axi_awready), .s_axi_wdata (s_axi_wdata),
        .s_axi_wstrb (s_axi_wstrb), .s_axi_wvalid (s_axi_wvalid),
        .s_axi_wready (s_axi_wready), .s_axi_bresp (s_axi_bresp),
        .s_axi_bvalid (s_axi_bvalid), .s_axi_bready (s_axi_bready),
        .s_axi_araddr (s_axi_araddr), .s_axi_arvalid (s_axi_arvalid),
        .s_axi_arready (s_axi_arready), .s_axi_rdata (s_axi_rdata),
        .s_axi_rresp (s_axi_rresp), .s_axi_rvalid (s_axi_rvalid),
        .s_axi_rready (s_axi_rready),
        .s_axis_tdata (s_axis_tdata), .s_axis_tkeep (s_axis_tkeep),
        .s_axis_tlast (s_axis_tlast), .s_axis_tvalid (s_axis_tvalid),
        .s_axis_tready (s_axis_tready),
        .m_axis_tdata (m_axis_tdata), .m_axis_tlast (m_axis_tlast),
        .m_axis_tvalid (m_axis_tvalid), .m_axis_tready (m_axis_tready)
    );

    // CTRL value: 3 = enable + soft reset in ONE write (what the driver does);
// 1 = enable only (control case, reset skipped).
    reg [31:0] CTRL_VALUE;
localparam integer NPKT = 4;
    localparam integer MSGS = 4;
    localparam integer PKT_BYTES = 12 + MSGS * 12;

    reg [7:0] img [0 : NPKT*PKT_BYTES - 1];

    integer i, j, b, q, k;
    integer beats_offered, beats_accepted;
    reg [63:0] wv;
    reg [63:0] pk_c, ms_c, gp_c;
    reg [31:0] er_c;

    task drive_all;
        begin
            beats_offered  = 0;
            beats_accepted = 0;
            q = 0;
            @(negedge aclk);
            while (q < NPKT*PKT_BYTES) begin
                wv = 64'd0;
                b  = 0;
                for (j = 0; j < 8; j = j + 1) begin
                    if (q + j < NPKT*PKT_BYTES) begin
                        wv[8*j +: 8] = img[q + j];
                        b = b + 1;
                    end
                end
                s_axis_tdata  = wv;
                s_axis_tkeep  = (b == 8) ? 8'hFF : ((8'hFF >> (8 - b)));
                s_axis_tlast  = (((q % PKT_BYTES) + b) >= PKT_BYTES);
                s_axis_tvalid = 1'b1;
                beats_offered = beats_offered + 1;

                @(posedge aclk);
                while (!s_axis_tready) @(posedge aclk);
                beats_accepted = beats_accepted + 1;
                @(negedge aclk);
                q = q + b;
            end
            s_axis_tvalid = 1'b0;
            s_axis_tkeep  = 8'h00;
            s_axis_tlast  = 1'b0;
        end
    endtask

    initial begin
        CTRL_VALUE = `CTRL_VAL;
        $display("  CTRL write = 0x%0h", CTRL_VALUE);
        for (i = 0; i < NPKT; i = i + 1) begin
            k = i * PKT_BYTES;
            img[k+0] = 8'h4E; img[k+1] = 8'h41; img[k+2] = 8'h53;
            img[k+3] = 8'h44; img[k+4] = 8'h41; img[k+5] = 8'h51;
            img[k+6] = 8'h30; img[k+7] = 8'h31;
            img[k+8]  = 8'h00; img[k+9]  = i[7:0];
            img[k+10] = 8'h00; img[k+11] = MSGS[7:0];
            for (q = 0; q < MSGS; q = q + 1) begin
                b = k + 12 + q*12;
                img[b+0] = 8'h00; img[b+1] = 8'h0A;
                img[b+2] = 8'h41;
                img[b+3] = 8'h00; img[b+4] = 8'h00;
                img[b+5] = 8'h00; img[b+6] = 8'h01;
                img[b+7] = 8'h00; img[b+8] = 8'h00;
                img[b+9] = 8'h02; img[b+10] = 8'h00; img[b+11] = 8'h03;
            end
        end

        aresetn = 0;
        repeat (20) @(posedge aclk);
        aresetn = 1;
        repeat (10) @(posedge aclk);

        fork
            begin
                @(negedge aclk);
                s_axi_awaddr  = 5'h18;
                s_axi_awvalid = 1;
                s_axi_wdata   = CTRL_VALUE;
                s_axi_wstrb   = 4'hF;
                s_axi_wvalid  = 1;
                @(posedge aclk);
                while (!(s_axi_awready && s_axi_wready)) @(posedge aclk);
                @(negedge aclk);
                s_axi_awvalid = 0;
                s_axi_wvalid  = 0;
            end
            drive_all;
        join

        repeat (600) @(posedge aclk);

        pk_c = dut.rx_packets;
        ms_c = dut.rx_messages;
        gp_c = dut.gap_count;
        er_c = dut.error_count;

        $display("NORESET pkts=%0d msgs=%0d gap=%0d err=%0d beats=%0d/%0d",
                 pk_c, ms_c, gp_c, er_c, beats_accepted, beats_offered);
        $display("  expected pkts=%0d msgs=%0d gap=0 err=0",
                 NPKT, NPKT*MSGS);
        if (pk_c == NPKT && ms_c == NPKT*MSGS && gp_c == 0 && er_c == 0)
            $display("NORESET-PASS");
        else
            $display("NORESET-FAIL");
        $finish;
    end

endmodule
